from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, event
from sqlalchemy.orm import relationship
from ..db.base import Base


class AuditLogImmutableException(Exception):
    """Raised when an attempt is made to update or delete an audit log row."""
    pass


class AuditLog(Base):
    """Append-only audit log table.

    Records who, when, before state, and after state for all critical operations.
    Protected at the ORM/DB event level against updates and deletes.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    actor = relationship("User", back_populates="audit_logs", foreign_keys=[actor_id])


# ORM-level immutability guard
@event.listens_for(AuditLog, "before_update")
def receive_before_update(mapper, connection, target):
    raise AuditLogImmutableException(
        f"AuditLog rows are append-only and cannot be modified (attempted update on id={target.id})."
    )


@event.listens_for(AuditLog, "before_delete")
def receive_before_delete(mapper, connection, target):
    raise AuditLogImmutableException(
        f"AuditLog rows are append-only and cannot be deleted (attempted delete on id={target.id})."
    )
