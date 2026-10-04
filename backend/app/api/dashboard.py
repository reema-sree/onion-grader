"""Analytics and Dashboard API Router for Staff and Admin monitoring."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.security import get_current_active_user, require_roles
from ..db import get_db
from ..models.centre import Centre
from ..models.grade_result import GradeResult
from ..models.lot import Lot, LotStatus
from ..models.onion_detection import OnionDetection
from ..models.user import User, UserRole
from ..schemas.lot import DashboardSummaryResponse, LotResponse
from ..api.lots import build_lot_response

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.CSC)),
):
    """Staff dashboard summary: today's scanned, approved, and pending counts, scoped to user's centre."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    query = db.query(Lot).filter(Lot.created_at >= today_start)
    centre_id = current_user.centre_id
    centre_name = current_user.centre.name if current_user.centre else None

    # Scope to centre if user is assigned to a centre (or staff/csc)
    if centre_id:
        query = query.filter(Lot.centre_id == centre_id)

    today_lots = query.all()
    scanned_today = len([l for l in today_lots if l.status != LotStatus.DRAFT])
    approved_today = len([l for l in today_lots if l.status in (LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED)])
    pending_today = len([l for l in today_lots if l.status == LotStatus.PENDING_REVIEW])

    return DashboardSummaryResponse(
        scanned_today=scanned_today,
        approved_today=approved_today,
        pending_today=pending_today,
        centre_id=centre_id,
        centre_name=centre_name,
    )


@router.get("/lots", response_model=List[LotResponse])
def get_dashboard_lots(
    centre_id: Optional[int] = Query(None, description="Filter by centre ID"),
    status: Optional[str] = Query(None, description="Filter by lot status: draft, pending_review, approved, overridden, reported, archived"),
    min_grade_a: Optional[float] = Query(None, description="Filter by minimum Grade A %"),
    search: Optional[str] = Query(None, description="Search farmer name or batch code"),
    days: Optional[int] = Query(None, description="Filter lots from past N days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.CSC)),
):
    """Filterable list of lots for staff and admin monitoring."""
    query = db.query(Lot)

    if centre_id:
        query = query.filter(Lot.centre_id == centre_id)
    elif current_user.role != UserRole.ADMIN and current_user.centre_id:
        query = query.filter(Lot.centre_id == current_user.centre_id)

    if status:
        query = query.filter(Lot.status == status)
    if search:
        term = f"%{search}%"
        query = query.filter((Lot.farmer_name.ilike(term)) | (Lot.batch_code.ilike(term)))
    if days:
        since_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Lot.created_at >= since_date)

    lots = query.order_by(Lot.created_at.desc()).all()

    results = []
    for lot in lots:
        resp = build_lot_response(lot)
        if min_grade_a is not None:
            if not resp.grade_result or resp.grade_result.grade_a_pct < min_grade_a:
                continue
        results.append(resp)

    return results


@router.get("/analytics")
def get_dashboard_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STAFF, UserRole.ADMIN, UserRole.CSC)),
):
    """Aggregate statistics: grade distribution over time, dispute/override rates, lots per centre."""
    total_lots = db.query(Lot).count()
    graded_lots = db.query(Lot).filter(Lot.status.in_([LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED])).count()

    # 1. Grade averages
    avg_grades = db.query(
        func.avg(GradeResult.grade_a_pct).label("avg_grade_a"),
        func.avg(GradeResult.urs_pct).label("avg_urs"),
        func.avg(GradeResult.defective_pct).label("avg_defective"),
        func.sum(GradeResult.total_count).label("total_onions_inspected"),
    ).first()

    avg_grade_a = round(float(avg_grades.avg_grade_a or 0.0), 2)
    avg_urs = round(float(avg_grades.avg_urs or 0.0), 2)
    avg_defective = round(float(avg_grades.avg_defective or 0.0), 2)
    total_onions = int(avg_grades.total_onions_inspected or 0)

    # 2. Overridden lots & dispute rate
    overridden_lots_count = db.query(Lot).filter(Lot.status == LotStatus.OVERRIDDEN).count()
    override_rate = round((overridden_lots_count / graded_lots * 100.0), 2) if graded_lots > 0 else 0.0

    # 3. Lots per centre distribution
    centre_stats = (
        db.query(Centre.id, Centre.name, func.count(Lot.id).label("lot_count"))
        .outerjoin(Lot, Lot.centre_id == Centre.id)
        .group_by(Centre.id, Centre.name)
        .all()
    )
    lots_per_centre = [
        {"centre_id": c.id, "centre_name": c.name, "lot_count": int(c.lot_count)}
        for c in centre_stats
    ]

    # 4. Grade distribution over time (last 7 days grouped)
    now = datetime.utcnow()
    timeline_days = []
    for i in range(6, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        day_start = datetime(day_date.year, day_date.month, day_date.day)
        day_end = day_start + timedelta(days=1)

        day_grades = (
            db.query(
                func.count(GradeResult.id).label("inspections"),
                func.avg(GradeResult.grade_a_pct).label("avg_grade_a"),
            )
            .filter(GradeResult.computed_at >= day_start, GradeResult.computed_at < day_end)
            .first()
        )
        timeline_days.append({
            "date": day_date.strftime("%Y-%m-%d"),
            "inspections": int(day_grades.inspections or 0),
            "avg_grade_a": round(float(day_grades.avg_grade_a or 0.0), 1),
        })

    return {
        "overview": {
            "total_lots": total_lots,
            "graded_lots": graded_lots,
            "total_onions_inspected": total_onions,
            "avg_grade_a_pct": avg_grade_a,
            "avg_urs_pct": avg_urs,
            "avg_defective_pct": avg_defective,
            "overridden_lots_count": overridden_lots_count,
            "override_dispute_rate_pct": override_rate,
        },
        "lots_per_centre": lots_per_centre,
        "timeline": timeline_days,
    }
