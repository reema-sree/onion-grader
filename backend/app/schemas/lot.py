"""Pydantic schemas for Lots, Images, Detections, Grading, Verifications, and Dashboards."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from ..models.lot import LotStatus
from ..models.image import ImageSource, CaptureMode


# ==========================================
# LOT CREATION & RESPONSES
# ==========================================

class LotCreate(BaseModel):
    centre_id: int
    farmer_id: Optional[int] = None
    farmer_name: Optional[str] = Field(None, max_length=255)
    crop: Optional[str] = "onion"
    batch_date: Optional[datetime] = None
    weight_kg: Optional[float] = Field(None, ge=0.0)
    lot_number: Optional[str] = Field(None, max_length=100)
    client_lot_id: Optional[str] = Field(None, max_length=100)


class CentreSimpleResponse(BaseModel):
    id: int
    code: str
    name: str
    district: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class ImageResponse(BaseModel):
    id: int
    lot_id: int
    storage_key: str
    sha256: str
    width: Optional[int] = None
    height: Optional[int] = None
    source: ImageSource
    captured_at: datetime
    capture_mode: CaptureMode

    model_config = ConfigDict(from_attributes=True)


class OnionDetectionResponse(BaseModel):
    id: int
    lot_id: int
    image_id: Optional[int] = None
    bbox: List[float]
    mask_polygon: Optional[List[List[float]]] = None
    original_class: str
    current_class: str
    bucket: str = "grade_a"  # grade_a, urs, defective
    confidence: float
    diameter_cm: Optional[float] = None
    is_overridden: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GradeResultResponse(BaseModel):
    id: int
    lot_id: int
    grade_a_pct: float
    urs_pct: float
    defective_pct: float = 0.0
    lot_grade: Optional[str] = None
    lot_grade_label: Optional[str] = None
    lot_grade_pct: Optional[float] = None
    total_count: int
    raw_counts: Dict[str, int]
    defect_breakdown: Dict[str, Dict[str, Any]]
    rule_version: str
    computed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationResponse(BaseModel):
    id: int
    lot_id: int
    verifier_id: Optional[int] = None
    decision: str
    ai_lot_grade: str
    final_lot_grade: str
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LotResponse(BaseModel):
    id: int
    batch_code: str
    client_lot_id: Optional[str] = None
    farmer_id: Optional[int] = None
    farmer_name: Optional[str] = None
    centre_id: int
    centre: Optional[CentreSimpleResponse] = None
    crop: str = "onion"
    batch_date: datetime
    weight_kg: Optional[float] = None
    needs_attention: bool = False
    attention_reason: Optional[str] = None
    ai_result: Optional[Dict[str, Any]] = None
    final_result: Optional[Dict[str, Any]] = None
    status: LotStatus
    created_at: datetime
    images: List[ImageResponse] = Field(default_factory=list)
    detections: List[OnionDetectionResponse] = Field(default_factory=list)
    grade_result: Optional[GradeResultResponse] = None
    verifications: List[VerificationResponse] = Field(default_factory=list)
    is_mock: bool = False

    model_config = ConfigDict(from_attributes=True)


class LotListResponse(BaseModel):
    items: List[LotResponse]
    total: int
    page: int
    size: int
    pages: int


# ==========================================
# VERIFICATION & OVERRIDES
# ==========================================

class LotVerifyRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'overridden'")
    new_grade: Optional[str] = Field(None, description="New lot grade when decision is overridden (e.g. Grade A, Defective, URS)")
    reason: Optional[str] = Field(None, description="Justification required when decision is overridden (min 10 characters)")


class DetectionOverrideItem(BaseModel):
    detection_id: int
    new_class: str = Field(..., description="good, damaged, rotten, sprouted, or undersized")


class FinalGradeOverrideItem(BaseModel):
    grade_a_pct: float = Field(..., ge=0.0, le=100.0)
    urs_pct: float = Field(..., ge=0.0, le=100.0)
    defective_pct: Optional[float] = Field(0.0, ge=0.0, le=100.0)


class LotOverrideRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=500, description="Justification required for audit trail (min 10 characters)")
    detection_overrides: Optional[List[DetectionOverrideItem]] = None
    final_grade_override: Optional[FinalGradeOverrideItem] = None


# ==========================================
# DASHBOARD SUMMARIES
# ==========================================

class DashboardSummaryResponse(BaseModel):
    scanned_today: int
    approved_today: int
    pending_today: int
    centre_id: Optional[int] = None
    centre_name: Optional[str] = None


class CentreGradeSummary(BaseModel):
    centre_id: int
    centre_code: str
    centre_name: str
    lot_count: int
    avg_grade_a_pct: float


class AdminSummaryResponse(BaseModel):
    total_batches: int
    total_centres: int
    avg_grade_a_pct: float
    override_rate: float
    per_centre_grade_a: List[CentreGradeSummary]
    period: str


# ==========================================
# ERROR / RETAKE GUIDANCE SCHEMA
# ==========================================

class QualityErrorDetail(BaseModel):
    error_code: str
    message: str
    guidance: str
