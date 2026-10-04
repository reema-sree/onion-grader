from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ..db.base import Base


class GradeResult(Base):
    __tablename__ = "grade_results"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    grade_a_pct = Column(Float, nullable=False)
    urs_pct = Column(Float, nullable=False)
    defective_pct = Column(Float, nullable=False, default=0.0)
    lot_grade = Column(String(50), nullable=True)  # E.g. "Grade A", "Defective", "URS"
    lot_grade_label = Column(String(100), nullable=True)  # E.g. "Grade A (72.5%)"
    lot_grade_pct = Column(Float, nullable=True)
    total_count = Column(Integer, nullable=False, default=0)
    raw_counts = Column(JSON, nullable=False, default=dict)
    defect_breakdown = Column(JSON, nullable=False, default=dict)
    rule_version = Column(String(50), nullable=False)
    computation_source = Column(String(50), nullable=False, default="server")  # "server" or "device"
    is_device_computed = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lot = relationship("Lot", back_populates="grade_results")
