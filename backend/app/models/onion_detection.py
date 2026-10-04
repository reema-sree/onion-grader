from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ..db.base import Base


class OnionDetection(Base):
    """Stores individual onion instance detections and segmentations.

    Original class is immutable upon creation. Manual overrides update
    current_class and bucket, and set is_overridden to True, recording the change in audit_log.
    """
    __tablename__ = "onion_detections"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=True, index=True)
    bbox = Column(JSON, nullable=False)  # [x1, y1, x2, y2]
    mask_polygon = Column(JSON, nullable=True)  # [[x, y], ...]
    original_class = Column(String(50), nullable=False)
    current_class = Column(String(50), nullable=False)
    bucket = Column(String(50), nullable=False, default="grade_a")  # "grade_a", "urs", "defective"
    confidence = Column(Float, nullable=False, default=1.0)
    diameter_cm = Column(Float, nullable=True)
    is_overridden = Column(Boolean, default=False, nullable=False)
    computation_source = Column(String(50), default="server", nullable=False)  # "server" or "device"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lot = relationship("Lot", back_populates="detections")
    image = relationship("Image", back_populates="detections")
