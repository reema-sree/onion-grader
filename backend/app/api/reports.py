"""Reports API Router handling report generation, versioning, superseding, and PDF downloads."""

import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.security import get_current_active_user
from ..db import get_db
from ..models.audit_log import AuditLog
from ..models.grade_result import GradeResult
from ..models.lot import Lot, LotStatus
from ..models.onion_detection import OnionDetection
from ..models.report import Report
from ..models.user import User
from ..schemas.report import ReportResponse
from ..services.audit import record_audit
from ..services.pdf_report import generate_lot_pdf_report
from ..services.report_hash import build_canonical_report_payload, compute_canonical_hash

router = APIRouter()


@router.post("/lots/{lot_id}/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def generate_report(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user),
):
    """Generate a tamper-evident PDF inspection report for a graded lot.

    Computes a canonical SHA-256 hash and handles superseding of older reports.
    """
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lot with ID {lot_id} not found."
        )

    if lot.status not in (LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report generation is only allowed when status is approved or overridden."
        )

    # Fetch latest grade result
    grade_res = (
        db.query(GradeResult)
        .filter(GradeResult.lot_id == lot.id)
        .order_by(GradeResult.computed_at.desc())
        .first()
    )
    if not grade_res:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No grade result found for this lot. Please run /grade first."
        )

    detections = db.query(OnionDetection).filter(OnionDetection.lot_id == lot.id).all()

    # Determine version and find previous active report
    existing_reports = (
        db.query(Report)
        .filter(Report.lot_id == lot.id)
        .order_by(Report.version.desc())
        .all()
    )
    version = (existing_reports[0].version + 1) if existing_reports else 1
    previous_active = next((r for r in existing_reports if r.superseded_by is None), None)

    # Mock mode detection
    is_mock = os.getenv("MOCK_MODEL", "false").lower() in ("true", "1", "yes")

    # Build canonical payload and compute SHA-256 hash
    canonical_payload = build_canonical_report_payload(
        lot=lot,
        grade_result=grade_res,
        detections=detections,
        version=version,
    )
    report_hash = compute_canonical_hash(canonical_payload)

    # Create new Report record
    new_report = Report(
        lot_id=lot.id,
        version=version,
        report_hash=report_hash,
        rule_version=grade_res.rule_version,
        is_mock=is_mock,
        generated_by=current_user.id if current_user else None,
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)

    # If an older active report exists, mark it superseded by the new one
    if previous_active:
        previous_active.superseded_by = new_report.id
        db.commit()

    # Generate physical PDF
    pdf_path = generate_lot_pdf_report(
        lot=lot,
        grade_result=grade_res,
        detections=detections,
        report=new_report,
    )
    new_report.pdf_path = str(pdf_path.as_posix())
    lot.status = LotStatus.REPORTED
    db.commit()

    # Record in AuditLog
    record_audit(
        db=db,
        action="generate_report",
        entity_type="report",
        entity_id=new_report.id,
        actor_id=current_user.id if current_user else None,
        before=None,
        after={
            "report_id": new_report.id,
            "lot_id": lot.id,
            "version": version,
            "report_hash": report_hash,
            "is_mock": is_mock,
            "superseded_report_id": previous_active.id if previous_active else None,
        },
        reason="Report generated",
    )
    db.commit()
    db.refresh(new_report)

    return ReportResponse.model_validate(new_report)


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve metadata for a specific report."""
    rep = db.query(Report).filter(Report.id == report_id).first()
    if not rep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report #{report_id} not found."
        )
    return ReportResponse.model_validate(rep)


@router.get("/reports/{report_id}/download")
def download_report_pdf(
    report_id: int,
    db: Session = Depends(get_db),
):
    """Download the generated PDF document."""
    rep = db.query(Report).filter(Report.id == report_id).first()
    if not rep or not rep.pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report PDF #{report_id} not found."
        )

    file_p = Path(rep.pdf_path)
    if not file_p.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file missing from storage."
        )

    return FileResponse(
        path=str(file_p),
        media_type="application/pdf",
        filename=file_p.name,
    )
