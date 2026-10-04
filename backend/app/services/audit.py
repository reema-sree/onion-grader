"""Audit logging service.

Provides functions to record append-only audit trail records for all
entity creations, modifications, and overrides.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models.audit_log import AuditLog


def record_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: int,
    actor_id: Optional[int] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> AuditLog:
    """Record an append-only audit entry.

    Args:
        db: Active SQLAlchemy session
        action: Operation name (e.g., 'create', 'update', 'override', 'login')
        entity_type: Target entity table or type name (e.g., 'lot', 'user', 'detection')
        entity_id: Target entity ID
        actor_id: ID of user performing the action (None if system action)
        before: State dictionary prior to modification
        after: State dictionary following modification
        reason: Justification (required for manual overrides)

    Returns:
        Created AuditLog instance
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
    )
    db.add(entry)
    db.flush()
    return entry


def get_entity_audit_logs(
    db: Session,
    entity_type: str,
    entity_id: int
) -> List[AuditLog]:
    """Retrieve all audit history entries for a specific entity in chronological order."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
