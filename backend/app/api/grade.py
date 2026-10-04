"""Grade API router."""
from typing import Any, Dict, List
from fastapi import APIRouter
from ..services.grading import compute_grade

router = APIRouter()


@router.post("/compute", response_model=Dict[str, Any])
def compute_grade_endpoint(onions: List[Dict[str, Any]]):
    """Compute grading breakdown for a list of detected onions."""
    return compute_grade(onions)
