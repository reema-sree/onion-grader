from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from ..db.base import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    superseded_by = Column(Integer, ForeignKey("reports.id", ondelete="SET NULL"), nullable=True)
    pdf_path = Column(String(500), nullable=True)
    report_hash = Column(String(64), nullable=True, index=True)
    rule_version = Column(String(50), nullable=False)
    is_mock = Column(Boolean, default=False, nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lot = relationship("Lot", back_populates="reports")
    generator = relationship("User", back_populates="reports", foreign_keys=[generated_by])
    superseded_report = relationship("Report", remote_side=[id], foreign_keys=[superseded_by])
