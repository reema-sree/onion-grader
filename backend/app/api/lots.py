"""Lots API router handling Lot lifecycle, image uploads, AI grading, verification, and farmer queries."""

import hashlib
import math
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import get_current_active_user, require_roles
from ..db import get_db
from ..models.audit_log import AuditLog
from ..models.centre import Centre
from ..models.grade_result import GradeResult
from ..models.image import CaptureMode, Image, ImageSource
from ..models.lot import Lot, LotStatus
from ..models.onion_detection import OnionDetection
from ..models.report import Report
from ..models.user import User, UserRole
from ..models.verification import Verification, VerificationDecision
from ..schemas.lot import (
    GradeResultResponse,
    ImageResponse,
    LotCreate,
    LotListResponse,
    LotOverrideRequest,
    LotResponse,
    LotVerifyRequest,
    OnionDetectionResponse,
    QualityErrorDetail,
    VerificationResponse,
)
from ..schemas.sync import (
    OfflineLotSyncRequest,
    SendSMSRequest,
    SendSMSResponse,
)
from ..services.audit import record_audit
from ..services.batch_code import generate_batch_code
from ..services.grading import compute_grade, determine_onion_bucket
from ..services.sms import send_report_sms


router = APIRouter()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def get_lot_or_404(lot_id: int, db: Session) -> Lot:
    """Helper to fetch a lot by ID or raise HTTP 404."""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with ID {lot_id} not found."
        )
    return lot


def build_lot_response(lot: Lot) -> LotResponse:
    """Helper to serialize a Lot with all child relations."""
    grade_res_data = None
    if lot.grade_results:
        latest_gr = sorted(lot.grade_results, key=lambda x: x.computed_at, reverse=True)[0]
        grade_res_data = GradeResultResponse.model_validate(latest_gr)

    # Check if mock mode was active
    is_mock = False
    if lot.reports and any(r.is_mock for r in lot.reports):
        is_mock = True
    elif os.getenv("MOCK_MODEL", "false").lower() in ("true", "1", "yes"):
        is_mock = True

    farmer_name_display = lot.farmer.name if lot.farmer else (lot.farmer_name or "Farmer")

    return LotResponse(
        id=lot.id,
        batch_code=lot.batch_code or lot.lot_number or f"LOT-{lot.id}",
        client_lot_id=lot.client_lot_id,
        farmer_id=lot.farmer_id,
        farmer_name=farmer_name_display,
        centre_id=lot.centre_id,
        centre=lot.centre,
        crop=lot.crop or "onion",
        batch_date=lot.batch_date or lot.created_at,
        weight_kg=lot.weight_kg,
        needs_attention=lot.needs_attention or False,
        attention_reason=lot.attention_reason,
        ai_result=lot.ai_result,
        final_result=lot.final_result,
        status=lot.status,
        created_at=lot.created_at,
        images=[ImageResponse.model_validate(img) for img in lot.images],
        detections=[OnionDetectionResponse.model_validate(det) for det in lot.detections],
        grade_result=grade_res_data,
        verifications=[VerificationResponse.model_validate(v) for v in lot.verifications],
        is_mock=is_mock,
    )


# ==============================================================================
# 1. LIST LOTS WITH FILTERS & PAGINATION
# ==============================================================================
@router.get("", response_model=LotListResponse)
def list_lots(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: draft, analysing, pending_review, approved, overridden, reported, archived"),
    centre_id: Optional[int] = Query(None, description="Filter by centre ID"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    lot_grade: Optional[str] = Query(None, description="Filter by assigned lot grade (e.g. 'Grade A', 'Defective', 'URS')"),
    farmer_id: Optional[int] = Query(None, description="Filter by farmer ID"),
    search: Optional[str] = Query(None, description="Search batch code or farmer name"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Retrieve lots with filtering and pagination."""
    query = db.query(Lot)

    if status_filter:
        query = query.filter(Lot.status == status_filter)
    if centre_id:
        query = query.filter(Lot.centre_id == centre_id)
    if farmer_id:
        query = query.filter(Lot.farmer_id == farmer_id)
    if date_from:
        query = query.filter(Lot.batch_date >= date_from)
    if date_to:
        query = query.filter(Lot.batch_date <= date_to)
    if search:
        term = f"%{search}%"
        query = query.outerjoin(User, Lot.farmer_id == User.id).filter(
            or_(
                Lot.batch_code.ilike(term),
                Lot.farmer_name.ilike(term),
                User.name.ilike(term)
            )
        )
    if lot_grade:
        query = query.join(GradeResult, GradeResult.lot_id == Lot.id).filter(
            GradeResult.lot_grade.ilike(f"%{lot_grade}%")
        )

    total = query.count()
    offset = (page - 1) * size
    lots = query.order_by(Lot.created_at.desc()).offset(offset).limit(size).all()
    pages = math.ceil(total / size) if total > 0 else 1

    return LotListResponse(
        items=[build_lot_response(l) for l in lots],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


# ==============================================================================
# 2. CREATE LOT
# ==============================================================================
@router.post("", response_model=LotResponse, status_code=status.HTTP_201_CREATED)
def create_lot(
    payload: LotCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Create a new onion lot with atomic per-year batch code (KS-{YYYY}-{5-digit sequence})."""
    centre = db.query(Centre).filter(Centre.id == payload.centre_id).first()
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Centre with ID {payload.centre_id} does not exist."
        )

    farmer_id = payload.farmer_id
    farmer_name = payload.farmer_name

    # If farmer_id given, resolve farmer name
    if farmer_id:
        farmer_user = db.query(User).filter(User.id == farmer_id).first()
        if farmer_user and not farmer_name:
            farmer_name = farmer_user.name
    elif not farmer_name:
        farmer_name = "Farmer"

    batch_code = generate_batch_code(db)

    new_lot = Lot(
        batch_code=batch_code,
        lot_number=payload.lot_number or batch_code,
        client_lot_id=payload.client_lot_id,
        farmer_id=farmer_id,
        farmer_name=farmer_name,
        centre_id=payload.centre_id,
        crop=payload.crop or "onion",
        batch_date=payload.batch_date or datetime.utcnow(),
        weight_kg=payload.weight_kg,
        status=LotStatus.DRAFT,
    )
    db.add(new_lot)
    db.commit()
    db.refresh(new_lot)

    record_audit(
        db=db,
        action="create_lot",
        entity_type="lot",
        entity_id=new_lot.id,
        actor_id=current_user.id if current_user else None,
        before=None,
        after={
            "id": new_lot.id,
            "batch_code": new_lot.batch_code,
            "farmer_name": new_lot.farmer_name,
            "centre_id": new_lot.centre_id,
            "weight_kg": new_lot.weight_kg,
            "status": new_lot.status.value,
        },
        reason="Lot creation",
    )
    db.commit()

    return build_lot_response(new_lot)


# ==============================================================================
# 3. OFFLINE IDEMPOTENT SYNC
# ==============================================================================
@router.post("/sync", response_model=LotResponse, status_code=status.HTTP_200_OK)
def sync_offline_lot(
    payload: OfflineLotSyncRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Idempotently sync an on-device/offline computed lot to the backend server."""
    existing_lot = db.query(Lot).filter(Lot.client_lot_id == payload.client_lot_id).first()
    if existing_lot:
        return build_lot_response(existing_lot)

    centre = db.query(Centre).filter(Centre.id == payload.centre_id).first()
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Centre #{payload.centre_id} not found."
        )

    batch_code = generate_batch_code(db)

    lot = Lot(
        batch_code=batch_code,
        client_lot_id=payload.client_lot_id,
        farmer_name=payload.farmer_name or "Farmer",
        centre_id=payload.centre_id,
        weight_kg=payload.weight_kg,
        lot_number=payload.lot_number or batch_code,
        status=LotStatus.APPROVED,
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)

    raw_onions = []
    for d in payload.detections:
        bucket = determine_onion_bucket(d.current_class, d.diameter_cm)
        det_row = OnionDetection(
            lot_id=lot.id,
            bbox=d.bbox,
            mask_polygon=d.mask_polygon,
            original_class=d.original_class,
            current_class=d.current_class,
            bucket=bucket,
            confidence=d.confidence,
            diameter_cm=d.diameter_cm,
            is_overridden=d.is_overridden,
            computation_source=payload.computation_source,
        )
        db.add(det_row)
        raw_onions.append({"class": d.current_class, "diameter_cm": d.diameter_cm})

    db.commit()

    grade_data = compute_grade(raw_onions)
    grade_row = GradeResult(
        lot_id=lot.id,
        grade_a_pct=grade_data["grade_a_pct"],
        urs_pct=grade_data["urs_pct"],
        defective_pct=grade_data["defective_pct"],
        lot_grade=grade_data["lot_grade"],
        lot_grade_label=grade_data["lot_grade_label"],
        lot_grade_pct=grade_data["lot_grade_pct"],
        total_count=grade_data["total_onions"],
        raw_counts=grade_data["raw_counts"],
        defect_breakdown=grade_data["defect_breakdown"],
        rule_version=grade_data["rule_version"],
        computation_source=payload.computation_source,
        is_device_computed=payload.is_device_computed,
    )
    db.add(grade_row)
    lot.ai_result = grade_data
    lot.final_result = grade_data
    db.commit()

    record_audit(
        db=db,
        action="offline_sync",
        entity_type="lot",
        entity_id=lot.id,
        actor_id=current_user.id if current_user else None,
        before=None,
        after={
            "batch_code": lot.batch_code,
            "client_lot_id": payload.client_lot_id,
            "lot_grade": grade_data["lot_grade"],
            "total_onions": grade_data["total_onions"],
        },
        reason="Offline lot synchronized",
    )
    db.commit()
    db.refresh(lot)

    return build_lot_response(lot)


# ==============================================================================
# 4. UPLOAD 1-3 IMAGES
# ==============================================================================
@router.post("/{id}/images", response_model=List[ImageResponse], status_code=status.HTTP_201_CREATED)
def upload_lot_images(
    id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Upload 1-3 images for an onion lot, validating MIME types, size, and integrity."""
    lot = get_lot_or_404(id, db)

    if len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least 1 image file."
        )

    existing_count = db.query(Image).filter(Image.lot_id == id).count()
    if existing_count + len(files) > 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A lot may have at most 3 images. Currently has {existing_count}, attempted to upload {len(files)}."
        )

    storage_root = Path(settings.STORAGE_DIR) / "lots" / str(lot.id)
    storage_root.mkdir(parents=True, exist_ok=True)

    saved_images: List[Image] = []

    for file in files:
        content_type = file.content_type or ""
        if content_type.lower() not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type '{content_type}' for {file.filename}. Allowed: JPEG, PNG, WebP."
            )

        file_bytes = file.file.read()
        if len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} is empty."
            )
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} exceeds maximum allowed size of 15MB."
            )

        sha256 = hashlib.sha256(file_bytes).hexdigest()

        nparr = np.frombuffer(file_bytes, np.uint8)
        img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_cv is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not decode image {file.filename}. File might be corrupted."
            )

        height, width = img_cv.shape[:2]
        file_ext = Path(file.filename or "image.jpg").suffix or ".jpg"
        save_path = storage_root / f"{sha256}{file_ext}"
        save_path.write_bytes(file_bytes)

        image_record = Image(
            lot_id=lot.id,
            storage_key=str(save_path.as_posix()),
            sha256=sha256,
            width=width,
            height=height,
            source=ImageSource.UPLOAD,
            capture_mode=CaptureMode.ONLINE,
        )
        db.add(image_record)
        saved_images.append(image_record)

    db.commit()

    for img in saved_images:
        db.refresh(img)
        record_audit(
            db=db,
            action="upload_image",
            entity_type="image",
            entity_id=img.id,
            actor_id=current_user.id if current_user else None,
            before=None,
            after={"lot_id": lot.id, "sha256": img.sha256, "storage_key": img.storage_key},
            reason="Image upload",
        )
    db.commit()

    return [ImageResponse.model_validate(img) for img in saved_images]


# ==============================================================================
# 5. RUN AI GRADING FLOW (starts pipeline, returns 202 immediately)
# ==============================================================================
@router.post(
    "/{id}/grade",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Grading started; poll GET /lots/{id}/grade/status for progress"},
        422: {
            "model": QualityErrorDetail,
            "description": "Pipeline stage failed — includes stage name and retake instructions",
        },
    },
)
def grade_lot(
    id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """
    Start the six-stage grading pipeline on the lot's uploaded images.

    The lot status changes to `analysing` immediately.
    Poll `GET /lots/{id}/grade/status` for per-stage progress.
    On completion the status becomes `pending_review`.

    If any stage fails (blur, no marker, no onions, overlap), the response
    is HTTP 422 with the failed stage name and a plain-language retake message.
    """
    from ..services.pipeline import GradingPipeline, initial_stage_list
    from ..core.config import load_grading_rules

    lot = get_lot_or_404(id, db)

    if not lot.images or len(lot.images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images uploaded for this lot. Please upload 1-3 images before grading.",
        )

    # Mark as analysing immediately
    lot.status = LotStatus.ANALYSING
    lot.ai_result = {"pipeline_stages": initial_stage_list(), "overall_percent": 0}
    db.commit()

    # Clear previous results
    db.query(OnionDetection).filter(OnionDetection.lot_id == lot.id).delete()
    db.query(GradeResult).filter(GradeResult.lot_id == lot.id).delete()
    db.commit()

    # Load pipeline config from grading_rules.yaml
    try:
        rules = load_grading_rules()
        pipeline = GradingPipeline(
            marker_side_cm=rules.marker_side_cm,
            min_onion_count=rules.min_onion_count,
            min_confidence=rules.min_confidence,
            blur_threshold=rules.blur_threshold,
        )
    except Exception:
        pipeline = GradingPipeline()  # use defaults

    # ── Run pipeline over each image, merge results ────────────────────────
    all_detections: list = []
    all_raw_onions: list = []
    is_any_mock = False
    merged_stages = None
    merged_retake = None
    failed_stage_name = None

    for img_record in lot.images:
        img_path = Path(img_record.storage_key)
        if not img_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image file missing on disk: {img_record.storage_key}",
            )
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not load image: {img_record.storage_key}",
            )

        pipe_result = pipeline.run(img_bgr)

        # Store live stage progress on the lot
        stage_snapshot = pipe_result.to_status_dict()
        lot.ai_result = {
            **(lot.ai_result or {}),
            "pipeline_stages": stage_snapshot["stages"],
            "overall_percent": stage_snapshot["overall_percent"],
        }
        db.commit()

        if pipe_result.is_mock:
            is_any_mock = True

        if pipe_result.failed_stage:
            failed_stage_name = pipe_result.failed_stage
            merged_retake = pipe_result.retake_message
            merged_stages = pipe_result.stages
            break

        # Merge detections from all images
        for det in pipe_result.detections:
            cls_name = det.get("class", "good")
            diameter = det.get("diameter_cm")
            confidence = det.get("confidence", 1.0)
            bbox = det.get("bbox", [0, 0, 0, 0])
            mask_polygon = det.get("mask_polygon")
            bucket = determine_onion_bucket(cls_name, diameter)

            det_row = OnionDetection(
                lot_id=lot.id,
                image_id=img_record.id,
                bbox=bbox,
                mask_polygon=mask_polygon,
                original_class=cls_name,
                current_class=cls_name,
                bucket=bucket,
                confidence=confidence,
                diameter_cm=diameter,
                is_overridden=False,
                computation_source="server",
            )
            db.add(det_row)
            all_detections.append(det_row)
            all_raw_onions.append({"class": cls_name, "diameter_cm": diameter})

        # Propagate needs_attention from any image
        if pipe_result.needs_attention and not lot.needs_attention:
            lot.needs_attention = True
            lot.attention_reason = pipe_result.attention_reason

        merged_stages = pipe_result.stages

    # ── Handle pipeline failure ────────────────────────────────────────────
    if failed_stage_name:
        lot.status = LotStatus.DRAFT  # Reset so user can retry after fixing
        lot.ai_result = {
            "pipeline_stages": [s.to_dict() for s in (merged_stages or [])],
            "overall_percent": 0,
            "failed_stage": failed_stage_name,
            "retake_message": merged_retake,
        }
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "failed_stage": failed_stage_name,
                "retake_message": merged_retake,
                "stages": [s.to_dict() for s in (merged_stages or [])],
            },
        )

    db.commit()

    # ── Compute final grade ────────────────────────────────────────────────
    grade_data = compute_grade(all_raw_onions)
    grade_result_row = GradeResult(
        lot_id=lot.id,
        grade_a_pct=grade_data["grade_a_pct"],
        urs_pct=grade_data["urs_pct"],
        defective_pct=grade_data["defective_pct"],
        lot_grade=grade_data["lot_grade"],
        lot_grade_label=grade_data["lot_grade_label"],
        lot_grade_pct=grade_data["lot_grade_pct"],
        total_count=grade_data["total_onions"],
        raw_counts=grade_data["raw_counts"],
        defect_breakdown=grade_data["defect_breakdown"],
        rule_version=grade_data["rule_version"],
        computation_source="server",
        is_device_computed=False,
    )
    db.add(grade_result_row)

    lot.ai_result = {
        **grade_data,
        "pipeline_stages": [s.to_dict() for s in (merged_stages or [])],
        "overall_percent": 100,
        "is_mock": is_any_mock,
    }
    lot.final_result = grade_data
    lot.status = LotStatus.PENDING_REVIEW
    db.commit()

    record_audit(
        db=db,
        action="grade_lot",
        entity_type="lot",
        entity_id=lot.id,
        actor_id=current_user.id if current_user else None,
        before={"status": LotStatus.ANALYSING.value},
        after={
            "status": LotStatus.PENDING_REVIEW.value,
            "grade_a_pct": grade_data["grade_a_pct"],
            "urs_pct": grade_data["urs_pct"],
            "defective_pct": grade_data["defective_pct"],
            "lot_grade": grade_data["lot_grade"],
            "total_onions": grade_data["total_onions"],
            "is_mock": is_any_mock,
            "needs_attention": lot.needs_attention,
        },
        reason="Automated AI grading completed; pending review",
    )
    db.commit()
    db.refresh(lot)

    return build_lot_response(lot)


# ==============================================================================
# 5b. GRADE PIPELINE STATUS (poll during / after grading)
# ==============================================================================
@router.get("/{id}/grade/status")
def get_grade_status(
    id: int,
    db: Session = Depends(get_db),
):
    """
    Return the current six-stage pipeline status for a lot.

    Intended for UI polling after `POST /lots/{id}/grade`.
    Response shape is stable and identical to what the on-device pipeline emits.

    Returns
    -------
    {
        "lot_id": int,
        "lot_status": str,
        "overall_percent": int,
        "is_complete": bool,
        "failed_stage": str | null,
        "retake_message": str | null,
        "is_mock": bool,
        "stages": [
            { "name": str, "status": "pending|running|done|failed",
              "message": str, "percent": int }
        ]
    }
    """
    from ..services.pipeline import initial_stage_list, STAGE_NAMES

    lot = get_lot_or_404(id, db)
    ai = lot.ai_result or {}

    stages = ai.get("pipeline_stages") or initial_stage_list()
    overall_pct = ai.get("overall_percent", 0)
    failed_stage = ai.get("failed_stage")
    retake_message = ai.get("retake_message")
    is_mock = ai.get("is_mock", False)
    is_complete = (
        lot.status in (LotStatus.PENDING_REVIEW, LotStatus.APPROVED,
                       LotStatus.OVERRIDDEN, LotStatus.REPORTED)
        and overall_pct == 100
    )

    return {
        "lot_id": id,
        "lot_status": lot.status.value,
        "overall_percent": overall_pct,
        "is_complete": is_complete,
        "failed_stage": failed_stage,
        "retake_message": retake_message,
        "is_mock": is_mock,
        "stages": stages,
    }




# ==============================================================================
# 6. VERIFY LOT (STAFF ONLY: APPROVED / OVERRIDDEN)
# ==============================================================================
@router.post("/{id}/verify", response_model=LotResponse)
def verify_lot(
    id: int,
    payload: LotVerifyRequest,
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.CSC)),
):
    """Staff-only verification endpoint to approve AI grading or override the result with reason."""
    lot = get_lot_or_404(id, db)

    decision_norm = payload.decision.lower().strip()
    if decision_norm not in ("approved", "overridden"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be either 'approved' or 'overridden'."
        )

    ai_lot_grade = (lot.ai_result or {}).get("lot_grade", "Grade A")

    if decision_norm == "overridden":
        if not payload.reason or len(payload.reason.strip()) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A detailed reason (minimum 10 characters) is required when overriding a lot."
            )
        final_lot_grade = payload.new_grade or "URS"
        lot.status = LotStatus.OVERRIDDEN
        
        # Update final_result snapshot
        updated_final = dict(lot.final_result or lot.ai_result or {})
        updated_final["lot_grade"] = final_lot_grade
        updated_final["is_overridden"] = True
        updated_final["override_reason"] = payload.reason
        lot.final_result = updated_final

        # Update latest grade result record
        latest_gr = (
            db.query(GradeResult)
            .filter(GradeResult.lot_id == lot.id)
            .order_by(GradeResult.computed_at.desc())
            .first()
        )
        if latest_gr:
            latest_gr.lot_grade = final_lot_grade
            latest_gr.lot_grade_label = f"{final_lot_grade} (Overridden)"
    else: # approved
        final_lot_grade = ai_lot_grade
        lot.status = LotStatus.APPROVED
        lot.final_result = lot.ai_result

    # Add verification record
    ver_record = Verification(
        lot_id=lot.id,
        verifier_id=current_staff.id,
        decision=VerificationDecision.OVERRIDDEN if decision_norm == "overridden" else VerificationDecision.APPROVED,
        ai_lot_grade=ai_lot_grade,
        final_lot_grade=final_lot_grade,
        reason=payload.reason,
    )
    db.add(ver_record)
    db.commit()

    record_audit(
        db=db,
        action="verify_lot",
        entity_type="lot",
        entity_id=lot.id,
        actor_id=current_staff.id,
        before={"status": LotStatus.PENDING_REVIEW.value, "ai_lot_grade": ai_lot_grade},
        after={"status": lot.status.value, "final_lot_grade": final_lot_grade, "decision": decision_norm},
        reason=payload.reason or "Lot grading verified and approved",
    )
    db.commit()
    db.refresh(lot)

    return build_lot_response(lot)


# ==============================================================================
# 7. GET LOT BY ID
# ==============================================================================
@router.get("/{id}", response_model=LotResponse)
def get_lot(
    id: int,
    db: Session = Depends(get_db),
):
    """Retrieve full lot details including images, detections, grade results, and verification history."""
    lot = get_lot_or_404(id, db)
    return build_lot_response(lot)


# ==============================================================================
# 8. LEGACY OVERRIDE ENDPOINT (REDIRECTS / APPLIES STAFF OVERRIDE)
# ==============================================================================
@router.post("/{id}/override", response_model=LotResponse)
def override_lot_grade(
    id: int,
    payload: LotOverrideRequest,
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.CSC)),
):
    """Staff-only endpoint to override individual onion classes or final grade."""
    lot = get_lot_or_404(id, db)

    if not payload.reason or len(payload.reason.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A justification reason (minimum 10 characters) is required for all manual overrides."
        )

    detection_changes = []
    if payload.detection_overrides:
        for ovr in payload.detection_overrides:
            det = (
                db.query(OnionDetection)
                .filter(OnionDetection.id == ovr.detection_id, OnionDetection.lot_id == lot.id)
                .first()
            )
            if not det:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Detection ID {ovr.detection_id} not found in Lot {lot.id}."
                )

            before_state = {
                "detection_id": det.id,
                "current_class": det.current_class,
                "bucket": det.bucket,
                "is_overridden": det.is_overridden,
            }

            det.current_class = ovr.new_class.lower().strip()
            det.bucket = determine_onion_bucket(det.current_class, det.diameter_cm)
            det.is_overridden = True

            after_state = {
                "detection_id": det.id,
                "current_class": det.current_class,
                "bucket": det.bucket,
                "is_overridden": det.is_overridden,
            }
            detection_changes.append({"before": before_state, "after": after_state})

        db.commit()

        all_dets = db.query(OnionDetection).filter(OnionDetection.lot_id == lot.id).all()
        onions_for_recompute = [
            {"current_class": d.current_class, "diameter_cm": d.diameter_cm}
            for d in all_dets
        ]
        recomputed = compute_grade(onions_for_recompute)

        latest_gr = (
            db.query(GradeResult)
            .filter(GradeResult.lot_id == lot.id)
            .order_by(GradeResult.computed_at.desc())
            .first()
        )
        if latest_gr:
            latest_gr.grade_a_pct = recomputed["grade_a_pct"]
            latest_gr.urs_pct = recomputed["urs_pct"]
            latest_gr.defective_pct = recomputed["defective_pct"]
            latest_gr.lot_grade = recomputed["lot_grade"]
            latest_gr.lot_grade_label = recomputed["lot_grade_label"]
            latest_gr.lot_grade_pct = recomputed["lot_grade_pct"]
            latest_gr.total_count = recomputed["total_onions"]
            latest_gr.raw_counts = recomputed["raw_counts"]
            latest_gr.defect_breakdown = recomputed["defect_breakdown"]
        lot.final_result = recomputed
        lot.status = LotStatus.OVERRIDDEN
        db.commit()

    if payload.final_grade_override:
        latest_gr = (
            db.query(GradeResult)
            .filter(GradeResult.lot_id == lot.id)
            .order_by(GradeResult.computed_at.desc())
            .first()
        )
        if latest_gr:
            latest_gr.grade_a_pct = payload.final_grade_override.grade_a_pct
            latest_gr.urs_pct = payload.final_grade_override.urs_pct
            latest_gr.defective_pct = payload.final_grade_override.defective_pct or 0.0
        lot.status = LotStatus.OVERRIDDEN
        db.commit()

    ai_grade = (lot.ai_result or {}).get("lot_grade", "Grade A")
    final_grade = (lot.final_result or {}).get("lot_grade", "URS")

    ver_record = Verification(
        lot_id=lot.id,
        verifier_id=current_staff.id,
        decision=VerificationDecision.OVERRIDDEN,
        ai_lot_grade=ai_grade,
        final_lot_grade=final_grade,
        reason=payload.reason,
    )
    db.add(ver_record)
    db.commit()

    record_audit(
        db=db,
        action="manual_override",
        entity_type="lot",
        entity_id=lot.id,
        actor_id=current_staff.id,
        before=None,
        after={
            "detection_changes": detection_changes,
            "final_grade_override": payload.final_grade_override.model_dump() if payload.final_grade_override else None,
        },
        reason=payload.reason,
    )
    db.commit()
    db.refresh(lot)

    return build_lot_response(lot)


# ==============================================================================
# 9. SEND SMS REPORT NOTICE
# ==============================================================================
@router.post("/{id}/send-sms", response_model=SendSMSResponse)
def dispatch_lot_sms(
    id: int,
    payload: Optional[SendSMSRequest] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Send short inspection report summary via SMS to farmer."""
    lot = get_lot_or_404(id, db)

    latest_gr = (
        db.query(GradeResult)
        .filter(GradeResult.lot_id == lot.id)
        .order_by(GradeResult.computed_at.desc())
        .first()
    )
    if not latest_gr:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lot must be graded before sending an SMS notice."
        )

    latest_report = (
        db.query(Report)
        .filter(Report.lot_id == lot.id, Report.superseded_by == None)
        .order_by(Report.version.desc())
        .first()
    )

    to_phone = (payload.to_phone if payload and payload.to_phone else None) or (lot.farmer.phone if lot.farmer else "+919876543210")

    sms_res = send_report_sms(
        to_phone=to_phone,
        lot=lot,
        grade_result=latest_gr,
        report=latest_report,
    )

    record_audit(
        db=db,
        action="send_sms",
        entity_type="lot",
        entity_id=lot.id,
        actor_id=current_user.id if current_user else None,
        before=None,
        after=sms_res,
        reason=f"SMS report dispatch to {to_phone}",
    )
    db.commit()

    return SendSMSResponse(**sms_res)
