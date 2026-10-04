"""Admin Management API Router for User, Centre, Summary, Grading Rules, and Audit Log."""

import csv
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, desc, and_, or_
from sqlalchemy.orm import Session

from ..core.config import DEFAULT_GRADING_RULES_PATH, GradingRulesConfig, load_grading_rules
from ..core.security import get_password_hash, require_roles
from ..db import get_db
from ..models.audit_log import AuditLog
from ..models.centre import Centre
from ..models.grade_result import GradeResult
from ..models.lot import Lot, LotStatus
from ..models.user import User, UserRole
from ..schemas.auth import UserResponse
from ..schemas.lot import AdminSummaryResponse, CentreGradeSummary
from ..services.audit import record_audit

router = APIRouter()



# ==========================================
# SCHEMAS
# ==========================================
class CentreCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, description="Centre code (e.g. C01, C02)")
    name: str = Field(..., min_length=2, max_length=255)
    district: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class CentreUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    district: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class CentreResponse(BaseModel):
    id: int
    code: str
    name: str
    district: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GradingRulesUpdate(BaseModel):
    min_size_cm: float = Field(..., ge=0.0, description="Minimum diameter in cm for Grade A")
    grade_a_threshold: float = Field(70.0, ge=0.0, le=100.0, description="Grade A lot threshold %")
    defective_threshold: float = Field(30.0, ge=0.0, le=100.0, description="Defective lot threshold %")
    grade_a_definition: Optional[str] = Field("Grade A: Healthy onions meeting size spec")
    urs_definition: Optional[str] = Field("URS: Healthy onions below size spec")
    class_bucket_mapping: Optional[Dict[str, str]] = None
    defect_classes: List[str] = Field(
        default_factory=lambda: ["good", "damaged", "rotten", "sprouted", "undersized"]
    )
    lot_grade_rules: Optional[List[Dict[str, Any]]] = None
    version: str = Field(..., description="New version label (e.g. v2.1)")
    change_note: Optional[str] = Field("Updated grading rules version", description="Change note for this version")



class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    password: Optional[str] = Field(None, min_length=6)
    role: UserRole = UserRole.FARMER
    centre_id: Optional[int] = None
    preferred_language: str = Field("en", max_length=10)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    centre_id: Optional[int] = None
    is_active: Optional[bool] = None


class AuditLogResponse(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: int
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



# ==========================================
# 1. ADMIN SUMMARY
# ==========================================
@router.get("/summary", response_model=AdminSummaryResponse)
def get_admin_summary(
    period: str = Query("all", description="Time period filter: '7d', '30d', or 'all'"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin summary KPI metrics: total batches, centres, average Grade A %, override rate, and per-centre breakdown."""
    now = datetime.utcnow()
    query = db.query(Lot)

    if period == "7d":
        since_date = now - timedelta(days=7)
        query = query.filter(Lot.created_at >= since_date)
    elif period == "30d":
        since_date = now - timedelta(days=30)
        query = query.filter(Lot.created_at >= since_date)

    lots = query.all()
    total_batches = len(lots)
    total_centres = db.query(Centre).filter(Centre.is_active == True).count()

    graded_lots = [l for l in lots if l.status in (LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED)]
    overridden_lots = [l for l in lots if l.status == LotStatus.OVERRIDDEN]
    
    override_rate = round((len(overridden_lots) / len(graded_lots) * 100.0), 2) if graded_lots else 0.0

    # Calculate average Grade A % across graded batches
    grade_a_pcts = []
    for l in graded_lots:
        if l.final_result and "grade_a_pct" in l.final_result:
            grade_a_pcts.append(float(l.final_result["grade_a_pct"]))
        elif l.grade_results:
            grade_a_pcts.append(float(l.grade_results[-1].grade_a_pct))

    avg_grade_a = round(sum(grade_a_pcts) / len(grade_a_pcts), 2) if grade_a_pcts else 0.0

    # Per-centre breakdown
    all_centres = db.query(Centre).order_by(Centre.id.asc()).all()
    per_centre_list: List[CentreGradeSummary] = []

    for c in all_centres:
        c_lots = [l for l in lots if l.centre_id == c.id]
        c_graded = [l for l in c_lots if l.status in (LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED)]
        c_pcts = []
        for l in c_graded:
            if l.final_result and "grade_a_pct" in l.final_result:
                c_pcts.append(float(l.final_result["grade_a_pct"]))
            elif l.grade_results:
                c_pcts.append(float(l.grade_results[-1].grade_a_pct))
        
        c_avg = round(sum(c_pcts) / len(c_pcts), 2) if c_pcts else 0.0
        per_centre_list.append(
            CentreGradeSummary(
                centre_id=c.id,
                centre_code=c.code or f"C{c.id:02d}",
                centre_name=c.name,
                lot_count=len(c_lots),
                avg_grade_a_pct=c_avg,
            )
        )

    return AdminSummaryResponse(
        total_batches=total_batches,
        total_centres=total_centres,
        avg_grade_a_pct=avg_grade_a,
        override_rate=override_rate,
        per_centre_grade_a=per_centre_list,
        period=period,
    )


# ==========================================
# 2. USER MANAGEMENT
# ==========================================
@router.get("/users", response_model=List[UserResponse])
def list_users(
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    role: Optional[str] = Query(None, description="Filter by role: farmer|staff|csc|admin"),
    centre_id: Optional[int] = Query(None, description="Filter by centre"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: list all users with optional search and filter."""
    q = db.query(User)
    if search:
        s = f"%{search}%"
        q = q.filter(or_(User.name.ilike(s), User.email.ilike(s), User.phone.ilike(s)))
    if role:
        q = q.filter(User.role == role)
    if centre_id:
        q = q.filter(User.centre_id == centre_id)
    users = q.order_by(desc(User.created_at)).all()
    return [
        UserResponse(
            id=u.id,
            name=u.name,
            email=u.email,
            phone=u.phone,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            centre_id=u.centre_id,
            preferred_language=u.preferred_language,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: create a new user."""
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")
    if payload.phone and db.query(User).filter(User.phone == payload.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered.")

    hashed = get_password_hash(payload.password) if payload.password else None
    user = User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hashed,
        role=payload.role,
        centre_id=payload.centre_id,
        preferred_language=payload.preferred_language,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record_audit(db=db, action="create_user", entity_type="user", entity_id=user.id,
                 actor_id=current_admin.id, before=None,
                 after={"name": user.name, "role": user.role.value, "centre_id": user.centre_id},
                 reason="Admin user creation")
    db.commit()

    return UserResponse(id=user.id, name=user.name, email=user.email, phone=user.phone,
                        role=user.role.value, centre_id=user.centre_id,
                        preferred_language=user.preferred_language, is_active=user.is_active,
                        created_at=user.created_at)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: update a user's name, role, centre assignment, or active status."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User #{user_id} not found.")
    if user.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    before = {"name": user.name, "role": user.role.value, "centre_id": user.centre_id, "is_active": user.is_active}
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    if payload.centre_id is not None:
        user.centre_id = payload.centre_id
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)

    record_audit(db=db, action="update_user", entity_type="user", entity_id=user.id,
                 actor_id=current_admin.id, before=before,
                 after={"name": user.name, "role": user.role.value, "centre_id": user.centre_id, "is_active": user.is_active},
                 reason="Admin user update")
    db.commit()

    return UserResponse(id=user.id, name=user.name, email=user.email, phone=user.phone,
                        role=user.role.value, centre_id=user.centre_id,
                        preferred_language=user.preferred_language, is_active=user.is_active,
                        created_at=user.created_at)




@router.post("/users/{user_id}/toggle-active", response_model=UserResponse)
def toggle_user_active_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin endpoint to activate or deactivate a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User #{user_id} not found.")

    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrators cannot deactivate their own account.")

    before_active = user.is_active
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    record_audit(
        db=db,
        action="toggle_user_active",
        entity_type="user",
        entity_id=user.id,
        actor_id=current_admin.id,
        before={"is_active": before_active},
        after={"is_active": user.is_active},
        reason=f"Admin toggled account active status to {user.is_active}",
    )
    db.commit()

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        centre_id=user.centre_id,
        preferred_language=user.preferred_language,
        is_active=user.is_active,
        created_at=user.created_at,
    )


# ==========================================
# 3. CENTRE MANAGEMENT
# ==========================================
@router.get("/centres", response_model=List[CentreResponse])
def list_centres(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF, UserRole.CSC)),
):
    """List all procurement centres."""
    return db.query(Centre).order_by(Centre.id.asc()).all()


@router.post("/centres", response_model=CentreResponse, status_code=status.HTTP_201_CREATED)
def create_centre(
    payload: CentreCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin endpoint to create a new procurement centre."""
    existing = db.query(Centre).filter((Centre.name == payload.name) | (Centre.code == payload.code)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Centre name or code already exists.")

    centre = Centre(
        code=payload.code,
        name=payload.name,
        district=payload.district,
        state=payload.state,
        address=payload.address,
        is_active=payload.is_active,
    )
    db.add(centre)
    db.commit()
    db.refresh(centre)

    record_audit(
        db=db,
        action="create_centre",
        entity_type="centre",
        entity_id=centre.id,
        actor_id=current_admin.id,
        before=None,
        after={"code": centre.code, "name": centre.name, "district": centre.district, "state": centre.state},
        reason="Admin centre creation",
    )
    db.commit()

    return centre


@router.patch("/centres/{centre_id}", response_model=CentreResponse)
def update_centre(
    centre_id: int,
    payload: CentreUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: edit a centre's details or deactivate it."""
    centre = db.query(Centre).filter(Centre.id == centre_id).first()
    if not centre:
        raise HTTPException(status_code=404, detail=f"Centre #{centre_id} not found.")

    before = {"name": centre.name, "district": centre.district, "state": centre.state, "is_active": centre.is_active}
    if payload.name is not None:
        centre.name = payload.name
    if payload.district is not None:
        centre.district = payload.district
    if payload.state is not None:
        centre.state = payload.state
    if payload.address is not None:
        centre.address = payload.address
    if payload.is_active is not None:
        centre.is_active = payload.is_active

    db.commit()
    db.refresh(centre)

    record_audit(db=db, action="update_centre", entity_type="centre", entity_id=centre.id,
                 actor_id=current_admin.id, before=before,
                 after={"name": centre.name, "district": centre.district, "is_active": centre.is_active},
                 reason="Admin centre update")
    db.commit()
    return centre


# ==========================================
# 4. GRADING RULES GOVERNANCE
# ==========================================
@router.get("/grading-rules", response_model=GradingRulesConfig)
def get_grading_rules(
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Fetch current active grading rules configuration."""
    return load_grading_rules()


@router.post("/grading-rules", response_model=GradingRulesConfig)
def update_grading_rules(
    payload: GradingRulesUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: update grading rules and save a new versioned snapshot to YAML."""
    old_rules = load_grading_rules()

    # Build updated lot_grade_rules from explicit thresholds if not provided
    lot_grade_rules = payload.lot_grade_rules or [
        {"grade": "Grade A", "condition": f"grade_a_pct >= {payload.grade_a_threshold}",
         "threshold": payload.grade_a_threshold},
        {"grade": "Defective", "condition": f"defective_pct >= {payload.defective_threshold}",
         "threshold": payload.defective_threshold},
        {"grade": "URS", "condition": "otherwise"},
    ]

    new_rules_dict = {
        "min_size_cm": payload.min_size_cm,
        "grade_a_definition": payload.grade_a_definition or old_rules.grade_a_definition,
        "urs_definition": payload.urs_definition or old_rules.urs_definition,
        "class_bucket_mapping": payload.class_bucket_mapping or old_rules.class_bucket_mapping,
        "defect_classes": payload.defect_classes,
        "lot_grade_rules": lot_grade_rules,
        "version": payload.version,
        # Preserve pipeline config fields
        "marker_side_cm": getattr(old_rules, "marker_side_cm", 5.0),
        "min_onion_count": getattr(old_rules, "min_onion_count", 2),
        "min_confidence": getattr(old_rules, "min_confidence", 0.60),
        "blur_threshold": getattr(old_rules, "blur_threshold", 40.0),
    }

    validated_rules = GradingRulesConfig(**new_rules_dict)

    with open(DEFAULT_GRADING_RULES_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(new_rules_dict, f, sort_keys=False)

    record_audit(
        db=db,
        action="update_grading_rules",
        entity_type="grading_rules",
        entity_id=0,
        actor_id=current_admin.id,
        before=old_rules.model_dump(),
        after=validated_rules.model_dump(),
        reason=f"[v{payload.version}] {payload.change_note}",
    )
    db.commit()

    return validated_rules


# ==========================================
# 5. AUDIT LOG (Read-Only)
# ==========================================
@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity_type (lot, user, centre, grading_rules)"),
    actor_id: Optional[int] = Query(None, description="Filter by actor user ID"),
    batch_code: Optional[str] = Query(None, description="Filter by batch code substring in reason/after"),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD start"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD end"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: reverse-chronological audit log with optional filters. Read-only."""
    q = db.query(AuditLog)

    if action:
        q = q.filter(AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if batch_code:
        # Search batch_code in the reason field (seed/verify write it there)
        q = q.filter(AuditLog.reason.ilike(f"%{batch_code}%"))
    if date_from:
        try:
            q = q.filter(AuditLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    logs = q.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit).all()

    result = []
    for log in logs:
        actor_name = None
        if log.actor:
            actor_name = log.actor.name
        result.append(AuditLogResponse(
            id=log.id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            actor_id=log.actor_id,
            actor_name=actor_name,
            before=log.before,
            after=log.after,
            reason=log.reason,
            created_at=log.created_at,
        ))
    return result


@router.get("/audit-logs/export")
def export_audit_logs_csv(
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    actor_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Admin: export audit log to CSV. Read-only, no pagination limit."""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if date_from:
        try:
            q = q.filter(AuditLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    logs = q.order_by(desc(AuditLog.created_at)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "actor_id", "actor_name", "action", "entity_type", "entity_id", "reason"])
    for log in logs:
        actor_name = log.actor.name if log.actor else ""
        writer.writerow([
            log.id,
            log.created_at.isoformat(),
            log.actor_id or "",
            actor_name,
            log.action,
            log.entity_type,
            log.entity_id,
            log.reason or "",
        ])

    output.seek(0)
    filename = f"kisan_setu_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
