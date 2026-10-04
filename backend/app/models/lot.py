from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from ..db.base import Base


class LotStatus(str, enum.Enum):
    DRAFT = "draft"
    ANALYSING = "analysing"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    OVERRIDDEN = "overridden"
    REPORTED = "reported"
    ARCHIVED = "archived"


class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    batch_code = Column(String(50), unique=True, index=True, nullable=False)  # KS-YYYY-XXXXX
    client_lot_id = Column(String(100), unique=True, index=True, nullable=True)  # Client UUID for idempotent sync
    lot_number = Column(String(100), index=True, nullable=True)
    farmer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    farmer_name = Column(String(255), nullable=True)  # Fallback display name
    centre_id = Column(Integer, ForeignKey("centres.id", ondelete="RESTRICT"), nullable=False, index=True)
    crop = Column(String(50), default="onion", nullable=False)
    batch_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    weight_kg = Column(Float, nullable=True)
    needs_attention = Column(Boolean, default=False, nullable=False)
    attention_reason = Column(String(500), nullable=True)
    ai_result = Column(JSON, nullable=True)  # AI buckets snapshot
    final_result = Column(JSON, nullable=True)  # Verified / final grade snapshot
    status = Column(
        SQLEnum(LotStatus, values_callable=lambda x: [e.value for e in x]),
        default=LotStatus.DRAFT,
        nullable=False,
        index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    centre = relationship("Centre", back_populates="lots")
    farmer = relationship("User", back_populates="lots", foreign_keys=[farmer_id])
    images = relationship("Image", back_populates="lot", cascade="all, delete-orphan")
    grade_results = relationship("GradeResult", back_populates="lot", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="lot", cascade="all, delete-orphan")
    detections = relationship("OnionDetection", back_populates="lot", cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="lot", cascade="all, delete-orphan")
