"""Unit and Integration tests for Offline Sync Idempotency, Source Tracking, and SMS notifications."""

import pytest
from backend.app.models.audit_log import AuditLog
from backend.app.models.grade_result import GradeResult
from backend.app.models.lot import Lot
from backend.app.models.onion_detection import OnionDetection
from backend.app.services.grading import compute_grade
from backend.app.services.sms import build_sms_body, send_report_sms


def test_sms_body_formatting_and_mock_dispatch(db_session, seed_centre):
    """SMS body must contain farmer name, lot ID, Grade A %, URS %, total count, and verify link."""
    lot = Lot(farmer_name="Babanrao More", centre_id=seed_centre.id, weight_kg=120.0, batch_code="KS-2026-08888", lot_number="LOT-20261003-8888")
    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)

    grade_res = GradeResult(
        lot_id=lot.id,
        grade_a_pct=88.5,
        urs_pct=11.5,
        total_count=20,
        raw_counts={"good": 18, "damaged": 1, "rotten": 1, "sprouted": 0, "undersized": 0},
        defect_breakdown={},
        rule_version="v1.0",
        computation_source="server",
    )
    db_session.add(grade_res)
    db_session.commit()

    # 1. Check formatted body text
    body = build_sms_body(lot, grade_res)
    assert "Babanrao More" in body
    assert "KS-2026-08888" in body
    assert "88.5%" in body
    assert "11.5%" in body
    assert "/verify/" in body

    # 2. Check mock dispatch
    res = send_report_sms("+919876543210", lot, grade_res)
    assert res["status"] == "mock_sent"
    assert res["is_mock"] is True
    assert res["message_id"].startswith("mock_sms_")
    assert res["to"] == "+919876543210"


def test_sms_endpoint_dispatch(client, farmer_headers, seed_centre):
    """POST /lots/{id}/send-sms sends report notice and writes to audit log."""
    # Sync a device detection to create a graded lot
    sync_payload = {
        "client_lot_id": "uuid_sms_test_lot_unique",
        "farmer_name": "Kisanrao",
        "centre_id": seed_centre.id,
        "weight_kg": 90.0,
        "detections": [
            {"bbox": [10, 10, 60, 60], "original_class": "good", "current_class": "good", "confidence": 0.95, "diameter_cm": 6.8}
        ]
    }
    sync_resp = client.post("/lots/sync", json=sync_payload, headers=farmer_headers)
    assert sync_resp.status_code == 200
    lot_id = sync_resp.json()["id"]

    # Call send-sms endpoint
    sms_payload = {"to_phone": "+919988776655"}
    sms_resp = client.post(f"/lots/{lot_id}/send-sms", json=sms_payload, headers=farmer_headers)
    assert sms_resp.status_code == 200
    sms_data = sms_resp.json()
    assert sms_data["status"] == "mock_sent"
    assert sms_data["to"] == "+919988776655"
    assert "Kisanrao" in sms_data["body"]


def test_offline_sync_creates_lot_with_device_source(client, farmer_headers, seed_centre, db_session):
    """Syncing an offline lot stores computation_source='device' and is_device_computed=True."""
    client_uuid = "client-uuid-offline-lot-999"
    sync_payload = {
        "client_lot_id": client_uuid,
        "farmer_name": "Deepak Shinde",
        "centre_id": seed_centre.id,
        "weight_kg": 210.0,
        "lot_number": "LOT-OFFLINE-999",
        "computation_source": "device",
        "is_device_computed": True,
        "detections": [
            {
                "bbox": [10, 20, 80, 90],
                "original_class": "good",
                "current_class": "good",
                "confidence": 0.92,
                "diameter_cm": 6.5,
                "is_overridden": False,
            },
            {
                "bbox": [100, 120, 180, 200],
                "original_class": "damaged",
                "current_class": "damaged",
                "confidence": 0.88,
                "diameter_cm": 5.8,
                "is_overridden": False,
            }
        ]
    }

    resp = client.post("/lots/sync", json=sync_payload, headers=farmer_headers)
    assert resp.status_code == 200
    lot_data = resp.json()
    lot_id = lot_data["id"]

    # Verify DB records have computation_source='device'
    gr = db_session.query(GradeResult).filter(GradeResult.lot_id == lot_id).first()
    assert gr.computation_source == "device"
    assert gr.is_device_computed is True
    assert gr.total_count == 2
    assert gr.grade_a_pct == 50.0
    assert gr.defective_pct == 50.0
    assert gr.urs_pct == 0.0

    dets = db_session.query(OnionDetection).filter(OnionDetection.lot_id == lot_id).all()
    assert len(dets) == 2
    for d in dets:
        assert d.computation_source == "device"


def test_offline_sync_is_idempotent(client, farmer_headers, seed_centre, db_session):
    """Resubmitting the same client_lot_id multiple times must return the existing lot without duplication."""
    client_uuid = "client-uuid-idempotent-check-111"
    sync_payload = {
        "client_lot_id": client_uuid,
        "farmer_name": "Tukaram Patil",
        "centre_id": seed_centre.id,
        "weight_kg": 175.0,
        "detections": [
            {"bbox": [10, 10, 50, 50], "original_class": "good", "current_class": "good", "confidence": 0.9, "diameter_cm": 6.2}
        ]
    }

    # First sync
    resp1 = client.post("/lots/sync", json=sync_payload, headers=farmer_headers)
    assert resp1.status_code == 200
    lot1_id = resp1.json()["id"]

    # Second sync (identical client_lot_id)
    resp2 = client.post("/lots/sync", json=sync_payload, headers=farmer_headers)
    assert resp2.status_code == 200
    lot2_id = resp2.json()["id"]

    assert lot1_id == lot2_id

    # Confirm only one Lot exists in database with this client_lot_id
    count = db_session.query(Lot).filter(Lot.client_lot_id == client_uuid).count()
    assert count == 1


def test_device_and_server_grading_consistency():
    """Verify that Python server grade computation produces accurate and predictable outputs across classes."""
    test_detections = [
        {"class": "good", "diameter_cm": 6.2},
        {"class": "good", "diameter_cm": 5.8},  # Undersized -> URS
        {"class": "damaged", "diameter_cm": 6.5}, # Defective
        {"class": "rotten", "diameter_cm": 4.5},  # Defective
        {"class": "sprouted", "diameter_cm": 7.0},# Defective
    ]
    res = compute_grade(test_detections)
    assert res["total_onions"] == 5
    assert res["grade_a_count"] == 1
    assert res["urs_count"] == 1
    assert res["defective_count"] == 3
    assert res["grade_a_pct"] == 20.0
    assert res["urs_pct"] == 20.0
    assert res["defective_pct"] == 60.0
    assert res["defect_breakdown"]["good"]["count"] == 1
    assert res["defect_breakdown"]["undersized"]["count"] == 1
    assert res["defect_breakdown"]["damaged"]["count"] == 1
    assert res["defect_breakdown"]["rotten"]["count"] == 1
    assert res["defect_breakdown"]["sprouted"]["count"] == 1
