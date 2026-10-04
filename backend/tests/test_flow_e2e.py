"""End-to-End integration tests for Lot Creation, Image Upload, AI Grading, and Staff Overrides."""

import io
import os
import cv2
import numpy as np
import pytest

from backend.app.models.audit_log import AuditLog
from backend.app.models.lot import LotStatus


def generate_test_image_bytes(width=640, height=480) -> bytes:
    """Generate a simple valid JPEG image in bytes."""
    img = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


def test_end_to_end_mock_grading_flow(
    client,
    farmer_headers,
    staff_headers,
    seed_centre,
    db_session,
    monkeypatch,
):
    """Full End-to-End flow:

    1. Create Lot (Farmer/Staff)
    2. Upload 2 images
    3. Run AI grading on Mock Mode
    4. Fetch full Lot details
    5. Staff overrides an onion class
    6. Verify original class preserved, grade recomputed, and audit log written
    """
    monkeypatch.setenv("MOCK_MODEL", "true")

    # -------------------------------------------------------------
    # 1. Create Lot
    # -------------------------------------------------------------
    lot_payload = {
        "farmer_name": "Kailas Shinde",
        "centre_id": seed_centre.id,
        "weight_kg": 250.0,
    }
    create_resp = client.post("/lots", json=lot_payload, headers=farmer_headers)
    assert create_resp.status_code == 201
    lot_data = create_resp.json()
    lot_id = lot_data["id"]
    assert lot_data["farmer_name"] == "Kailas Shinde"
    assert lot_data["status"] == "draft"
    assert lot_data["batch_code"].startswith("KS-")

    # -------------------------------------------------------------
    # 2. Upload Images
    # -------------------------------------------------------------
    img1_bytes = generate_test_image_bytes()
    img2_bytes = generate_test_image_bytes()

    files = [
        ("files", ("image1.jpg", io.BytesIO(img1_bytes), "image/jpeg")),
        ("files", ("image2.jpg", io.BytesIO(img2_bytes), "image/jpeg")),
    ]
    upload_resp = client.post(f"/lots/{lot_id}/images", files=files, headers=farmer_headers)
    assert upload_resp.status_code == 201
    uploaded_images = upload_resp.json()
    assert len(uploaded_images) == 2
    assert "storage_key" in uploaded_images[0]
    assert "sha256" in uploaded_images[0]

    # -------------------------------------------------------------
    # 3. Run AI Grading (now returns 202; poll grade/status)
    # -------------------------------------------------------------
    grade_resp = client.post(f"/lots/{lot_id}/grade", headers=farmer_headers)
    # Accept 200 (legacy sync) or 202 (new async)
    assert grade_resp.status_code in (200, 202)

    # Poll grade status until complete (pipeline is synchronous in test)
    status_resp = client.get(f"/lots/{lot_id}/grade/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "stages" in status_data
    assert len(status_data["stages"]) == 6  # six named stages
    assert status_data["overall_percent"] == 100
    assert status_data["is_complete"] is True
    assert status_data["failed_stage"] is None

    graded_lot = client.get(f"/lots/{lot_id}", headers=farmer_headers).json()
    assert graded_lot["status"] == "pending_review"
    assert len(graded_lot["detections"]) > 0
    assert graded_lot["grade_result"] is not None
    assert graded_lot["grade_result"]["total_count"] == len(graded_lot["detections"])
    gr = graded_lot["grade_result"]
    assert round(gr["grade_a_pct"] + gr["urs_pct"] + gr["defective_pct"], 2) == 100.0

    # -------------------------------------------------------------
    # 4. Fetch Full Lot Details (GET /lots/{id})
    # -------------------------------------------------------------
    get_resp = client.get(f"/lots/{lot_id}", headers=farmer_headers)
    assert get_resp.status_code == 200
    fetched_lot = get_resp.json()
    assert fetched_lot["id"] == lot_id
    assert len(fetched_lot["images"]) == 2
    assert len(fetched_lot["detections"]) == len(graded_lot["detections"])

    # -------------------------------------------------------------
    # 5. Non-Staff User Attempting Override -> Forbidden (403)
    # -------------------------------------------------------------
    target_detection = fetched_lot["detections"][0]
    override_payload = {
        "reason": "Farmer attempting manual override",
        "detection_overrides": [
            {"detection_id": target_detection["id"], "new_class": "damaged"}
        ],
    }
    forbidden_resp = client.post(f"/lots/{lot_id}/override", json=override_payload, headers=farmer_headers)
    assert forbidden_resp.status_code == 403

    # -------------------------------------------------------------
    # 6. Override Without Reason -> Bad Request (422 / 400)
    # -------------------------------------------------------------
    invalid_payload = {
        "reason": "",
        "detection_overrides": [
            {"detection_id": target_detection["id"], "new_class": "damaged"}
        ],
    }
    bad_req_resp = client.post(f"/lots/{lot_id}/override", json=invalid_payload, headers=staff_headers)
    assert bad_req_resp.status_code in (400, 422)

    # -------------------------------------------------------------
    # 7. Staff Override an Onion Class -> Success
    # -------------------------------------------------------------
    original_cls = target_detection["original_class"]
    valid_staff_override = {
        "reason": "Physical inspection detected skin damage and peeling",
        "detection_overrides": [
            {"detection_id": target_detection["id"], "new_class": "damaged"}
        ],
    }
    override_resp = client.post(f"/lots/{lot_id}/override", json=valid_staff_override, headers=staff_headers)
    assert override_resp.status_code == 200
    updated_lot = override_resp.json()

    # Find the modified detection
    modified_det = next(d for d in updated_lot["detections"] if d["id"] == target_detection["id"])
    assert modified_det["original_class"] == original_cls  # Original class preserved!
    assert modified_det["current_class"] == "damaged"      # Current class changed
    assert modified_det["is_overridden"] is True          # Overridden flag set

    # -------------------------------------------------------------
    # 8. Verify Audit Log Entry
    # -------------------------------------------------------------
    override_logs = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "lot",
        AuditLog.entity_id == lot_id,
        AuditLog.action == "manual_override"
    ).all()
    assert len(override_logs) >= 1
    latest_audit = override_logs[-1]
    assert latest_audit.reason == "Physical inspection detected skin damage and peeling"
    assert latest_audit.after["detection_changes"][0]["before"]["current_class"] == original_cls
    assert latest_audit.after["detection_changes"][0]["after"]["current_class"] == "damaged"
