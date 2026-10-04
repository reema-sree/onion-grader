"""Pydantic schemas for offline queue synchronization and SMS dispatch."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class OfflineDetectionItem(BaseModel):
    bbox: List[float] = Field(..., description="[x1, y1, x2, y2]")
    mask_polygon: Optional[List[List[float]]] = None
    original_class: str
    current_class: str
    confidence: float = 1.0
    diameter_cm: Optional[float] = None
    is_overridden: bool = False


class OfflineLotSyncRequest(BaseModel):
    client_lot_id: str = Field(..., description="Unique client-generated UUID for idempotent synchronization")
    farmer_name: str
    centre_id: int
    weight_kg: float = 0.0
    lot_number: Optional[str] = None
    computation_source: str = "device"
    is_device_computed: bool = True
    detections: List[OfflineDetectionItem] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    phone: Optional[str] = None


class SendSMSRequest(BaseModel):
    to_phone: Optional[str] = Field(None, description="Destination phone number; defaults to farmer/user phone if omitted")


class SendSMSResponse(BaseModel):
    status: str
    message_id: str
    to: str
    body: str
    is_mock: bool
    error: Optional[str] = None
