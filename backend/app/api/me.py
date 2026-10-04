"""Farmer Isolated Endpoints Router."""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..core.security import get_current_active_user
from ..db import get_db
from ..models.lot import Lot, LotStatus
from ..models.user import User
from ..schemas.lot import LotResponse
from ..api.lots import build_lot_response

router = APIRouter()


@router.get("/lots", response_model=List[LotResponse])
def get_my_lots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Farmer view: only approved, overridden, or reported lots belonging to the authenticated farmer.

    Farmers never see drafts or pending batches, and never another farmer's lots.
    """
    allowed_statuses = [LotStatus.APPROVED, LotStatus.OVERRIDDEN, LotStatus.REPORTED]
    lots = (
        db.query(Lot)
        .filter(Lot.farmer_id == current_user.id, Lot.status.in_(allowed_statuses))
        .order_by(Lot.created_at.desc())
        .all()
    )
    return [build_lot_response(l) for l in lots]
