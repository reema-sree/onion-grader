from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from ..db.base import Base


class VerificationDecision(str, enum.Enum):
    APPROVED = "approved"
    OVERRIDDEN = "overridden"


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    verifier_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    decision = Column(
        SQLEnum(VerificationDecision, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    ai_lot_grade = Column(String(50), nullable=False)
    final_lot_grade = Column(String(50), nullable=False)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lot = relationship("Lot", back_populates="verifications")
    verifier = relationship("User", back_populates="verifications")
