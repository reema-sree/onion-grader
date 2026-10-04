"""Pydantic schemas for Reports and Public Verification."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ReportResponse(BaseModel):
    id: int
    lot_id: int
    version: int
    superseded_by: Optional[int] = None
    pdf_path: Optional[str] = None
    report_hash: str
    rule_version: str
    is_mock: bool
    generated_by: Optional[int] = None
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportVerifyResponse(BaseModel):
    report_id: int
    lot_id: int
    lot_number: str
    farmer_name: str
    centre_name: str
    version: int
    status: str  # "VALID", "TAMPERED", "SUPERSEDED"
    is_valid: bool
    is_superseded: bool
    superseded_by_report_id: Optional[int] = None
    stored_hash: str
    computed_hash: str
    grade_a_pct: float
    urs_pct: float
    total_count: int
    generated_at: datetime
    is_mock: bool
    summary: str

    model_config = ConfigDict(from_attributes=True)
