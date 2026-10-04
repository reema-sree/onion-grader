"""Unit tests verifying append-only audit log service and DB/ORM-level immutability."""

import pytest
from backend.app.models.audit_log import AuditLog, AuditLogImmutableException
from backend.app.services.audit import record_audit, get_entity_audit_logs


def test_audit_log_creation(db_session, seed_farmer):
    """Verify that audit log entries can be created with before and after state."""
    entry = record_audit(
        db=db_session,
        action="update_status",
        entity_type="lot",
        entity_id=101,
        actor_id=seed_farmer.id,
        before={"status": "draft"},
        after={"status": "graded"},
        reason="Grading completed",
    )
    db_session.commit()

    assert entry.id is not None
    assert entry.actor_id == seed_farmer.id
    assert entry.action == "update_status"
    assert entry.before == {"status": "draft"}
    assert entry.after == {"status": "graded"}
    assert entry.reason == "Grading completed"

    logs = get_entity_audit_logs(db_session, "lot", 101)
    assert len(logs) == 1
    assert logs[0].id == entry.id


def test_audit_log_immutability_prevent_update(db_session, seed_farmer):
    """Verify that attempting to update an existing AuditLog row raises AuditLogImmutableException."""
    entry = record_audit(
        db=db_session,
        action="create_lot",
        entity_type="lot",
        entity_id=202,
        actor_id=seed_farmer.id,
        before=None,
        after={"weight_kg": 50.0},
        reason="Initial lot creation",
    )
    db_session.commit()

    # Attempt to update the existing audit entry
    entry.reason = "Tampered reason"
    with pytest.raises(AuditLogImmutableException) as exc_info:
        db_session.commit()

    assert "append-only and cannot be modified" in str(exc_info.value)
    db_session.rollback()


def test_audit_log_immutability_prevent_delete(db_session, seed_farmer):
    """Verify that attempting to delete an AuditLog row raises AuditLogImmutableException."""
    entry = record_audit(
        db=db_session,
        action="override_class",
        entity_type="onion_detection",
        entity_id=303,
        actor_id=seed_farmer.id,
        before={"class": "good"},
        after={"class": "damaged"},
        reason="Visual rot observed",
    )
    db_session.commit()

    # Attempt to delete the audit record
    db_session.delete(entry)
    with pytest.raises(AuditLogImmutableException) as exc_info:
        db_session.commit()

    assert "append-only and cannot be deleted" in str(exc_info.value)
    db_session.rollback()


def test_audit_log_created_on_registration_and_login(client, admin_headers, seed_centre, db_session):
    """Verify that register and login endpoints generate audit entries."""
    # 1. Register a new user
    user_payload = {
        "name": "Audit Test User",
        "email": "audittest@example.com",
        "password": "Password123!",
        "role": "farmer",
        "centre_id": seed_centre.id,
        "preferred_language": "en"
    }
    resp = client.post("/auth/register", json=user_payload, headers=admin_headers)
    assert resp.status_code == 201
    new_user_id = resp.json()["id"]

    # Check registration audit log
    reg_logs = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "user",
        AuditLog.entity_id == new_user_id,
        AuditLog.action == "create_user"
    ).all()
    assert len(reg_logs) == 1
    assert reg_logs[0].after["email"] == "audittest@example.com"

    # 2. Login as the newly created user
    login_resp = client.post("/auth/login", json={"email": "audittest@example.com", "password": "Password123!"})
    assert login_resp.status_code == 200

    # Check login audit log
    login_logs = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "user",
        AuditLog.entity_id == new_user_id,
        AuditLog.action == "login"
    ).all()
    assert len(login_logs) == 1
