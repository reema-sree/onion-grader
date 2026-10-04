from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from ..db.base import Base


class UserRole(str, enum.Enum):
    FARMER = "farmer"
    STAFF = "staff"
    CSC = "csc"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(
        SQLEnum(UserRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.FARMER,
        index=True
    )
    centre_id = Column(Integer, ForeignKey("centres.id", ondelete="SET NULL"), nullable=True)
    preferred_language = Column(String(10), default="en", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    centre = relationship("Centre", back_populates="users")
    lots = relationship("Lot", back_populates="farmer", foreign_keys="Lot.farmer_id")
    reports = relationship("Report", back_populates="generator", foreign_keys="Report.generated_by")
    audit_logs = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")
    verifications = relationship("Verification", back_populates="verifier", foreign_keys="Verification.verifier_id")
