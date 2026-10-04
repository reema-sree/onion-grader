"""Unit and Integration tests for Tamper-Evident Reports, Canonical Hashing, and Public Verification."""

import io
from pathlib import Path
import cv2
import numpy as np
import pytest

from backend.app.models.grade_result import GradeResult
from backend.app.models.lot import Lot, LotStatus
from backend.app.models.onion_detection import OnionDetection
from backend.app.models.report import Report
from backend.app.services.report_hash import (
    build_canonical_report_payload,
    compute_canonical_hash,
)


def generate_test_image_bytes(width=640, height=480) -> bytes:
    img = np.random.randint(50, 200, (height, width, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()


def test_canonical_hash_is_deterministic(db_session, seed_centre):
    """The canonical report hash must be 100% deterministic and sensitive to any modification."""
    lot = Lot(farmer_name="Ramesh Test", centre_id=seed_centre.id, weight_kg=100.0, batch_code="KS-2026-00099", status=LotStatus.APPROVED)
    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)

    grade_res = GradeResult(
        lot_id=lot.id,
        grade_a_pct=80.0,
        urs_pct=20.0,
        defective_pct=0.0,
        lot_grade="Grade A",
        total_count=10,
        raw_counts={"good": 8, "damaged": 2, "rotten": 0, "sprouted": 0, "undersized": 0},
        defect_breakdown={
            "good": {"count": 8, "pct": 80.0},
            "damaged": {"count": 2, "pct": 20.0},
            "rotten": {"count": 0, "pct": 0.0},
            "sprouted": {"count": 0, "pct": 0.0},
            "undersized": {"count": 0, "pct": 0.0},
        },
        rule_version="v2.0",
    )
    db_session.add(grade_res)
    db_session.commit()

    det1 = OnionDetection(
        lot_id=lot.id, image_id=1, bbox=[10, 10, 50, 50], original_class="good",
        current_class="good", bucket="grade_a", confidence=0.95, diameter_cm=6.5, is_overridden=False
    )
    db_session.add(det1)
    db_session.commit()

    # 1. Compute hash twice with same payload -> identical
    p1 = build_canonical_report_payload(lot, grade_res, [det1], version=1)
    p2 = build_canonical_report_payload(lot, grade_res, [det1], version=1)
    h1 = compute_canonical_hash(p1)
    h2 = compute_canonical_hash(p2)
    assert h1 == h2
    assert len(h1) == 64

    # 2. Modify a single float value -> hash changes
    grade_res.grade_a_pct = 80.01
    p3 = build_canonical_report_payload(lot, grade_res, [det1], version=1)
    h3 = compute_canonical_hash(p3)
    assert h1 != h3


def test_generate_pdf_report_and_public_verification(
    client,
    farmer_headers,
    staff_headers,
    seed_centre,
    monkeypatch,
):
    """E2E test: Grade lot, verify lot, generate PDF report with QR code, verify authenticity."""
    monkeypatch.setenv("MOCK_MODEL", "true")

    # 1. Create Lot
    lot_resp = client.post("/lots", json={"farmer_name": "Sanjay Rao", "centre_id": seed_centre.id, "weight_kg": 300.0}, headers=farmer_headers)
    lot_id = lot_resp.json()["id"]

    # 2. Upload Image
    img_bytes = generate_test_image_bytes()
    files = [("files", ("onion1.jpg", io.BytesIO(img_bytes), "image/jpeg"))]
    client.post(f"/lots/{lot_id}/images", files=files, headers=farmer_headers)

    # 3. Run AI Grading
    client.post(f"/lots/{lot_id}/grade", headers=farmer_headers)

    # 4. Staff Verifies / Approves
    client.post(f"/lots/{lot_id}/verify", json={"decision": "approved"}, headers=staff_headers)

    # 5. Generate PDF Report (POST /lots/{id}/report)
    rep_resp = client.post(f"/lots/{lot_id}/report", headers=staff_headers)
    assert rep_resp.status_code == 201
    rep_data = rep_resp.json()
    report_id = rep_data["id"]
    assert rep_data["version"] == 1
    assert rep_data["report_hash"] is not None
    assert rep_data["pdf_path"] is not None
    assert Path(rep_data["pdf_path"]).exists()

    # 6. Public JSON Verification (GET /verify/{report_id})
    verify_resp = client.get(f"/verify/{report_id}")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["status"] == "VALID"
    assert v_data["is_valid"] is True
    assert v_data["is_superseded"] is False
    assert v_data["stored_hash"] == v_data["computed_hash"]
    assert v_data["is_mock"] is True

    # 7. Public HTML Mobile Verification (GET /verify/{report_id}/view)
    html_resp = client.get(f"/verify/{report_id}/view")
    assert html_resp.status_code == 200
    assert "VERIFIED AUTHENTIC" in html_resp.text
    assert "DEMO DATA" in html_resp.text

    # 8. Download PDF (GET /reports/{report_id}/download)
    download_resp = client.get(f"/reports/{report_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert len(download_resp.content) > 1000


def test_tampering_with_stored_data_fails_verification(
    client,
    farmer_headers,
    staff_headers,
    seed_centre,
    db_session,
    monkeypatch,
):
    """Tampering with DB records after report generation triggers TAMPERED status."""
    monkeypatch.setenv("MOCK_MODEL", "true")

    # 1. Setup graded lot with report
    lot_resp = client.post("/lots", json={"farmer_name": "Original Farmer", "centre_id": seed_centre.id, "weight_kg": 150.0}, headers=farmer_headers)
    lot_id = lot_resp.json()["id"]

    files = [("files", ("o.jpg", io.BytesIO(generate_test_image_bytes()), "image/jpeg"))]
    client.post(f"/lots/{lot_id}/images", files=files, headers=farmer_headers)
    client.post(f"/lots/{lot_id}/grade", headers=farmer_headers)
    client.post(f"/lots/{lot_id}/verify", json={"decision": "approved"}, headers=staff_headers)

    rep_resp = client.post(f"/lots/{lot_id}/report", headers=staff_headers)
    report_id = rep_resp.json()["id"]

    # Verify initial valid state
    assert client.get(f"/verify/{report_id}").json()["status"] == "VALID"

    # 2. Tamper with DB: secretly change farmer name or Grade A %
    lot_db = db_session.query(Lot).filter(Lot.id == lot_id).first()
    lot_db.farmer_name = "Tampered Imposter Farmer"
    db_session.commit()

    # 3. Verification must now detect tampering
    tampered_resp = client.get(f"/verify/{report_id}")
    assert tampered_resp.status_code == 200
    v_data = tampered_resp.json()
    assert v_data["status"] == "TAMPERED"
    assert v_data["is_valid"] is False
    assert v_data["stored_hash"] != v_data["computed_hash"]
    assert "TAMPER" in v_data["summary"].upper()

    # 4. HTML view displays tampering warning
    html_resp = client.get(f"/verify/{report_id}/view")
    assert html_resp.status_code == 200
    assert "TAMPERING DETECTED" in html_resp.text


def test_override_after_report_creates_superseded_version(
    client,
    farmer_headers,
    staff_headers,
    seed_centre,
    monkeypatch,
):
    """When an override occurs and a new report is generated, the old report is marked superseded."""
    monkeypatch.setenv("MOCK_MODEL", "true")

    # 1. Setup graded lot & generate Report v1
    lot_resp = client.post("/lots", json={"farmer_name": "Anil Patil", "centre_id": seed_centre.id, "weight_kg": 200.0}, headers=farmer_headers)
    lot_id = lot_resp.json()["id"]

    files = [("files", ("o.jpg", io.BytesIO(generate_test_image_bytes()), "image/jpeg"))]
    client.post(f"/lots/{lot_id}/images", files=files, headers=farmer_headers)
    client.post(f"/lots/{lot_id}/grade", headers=farmer_headers)
    client.post(f"/lots/{lot_id}/verify", json={"decision": "approved"}, headers=staff_headers)

    rep1_resp = client.post(f"/lots/{lot_id}/report", headers=staff_headers)
    rep1_id = rep1_resp.json()["id"]
    assert rep1_resp.json()["version"] == 1

    # 2. Staff performs an override on detection #1
    lot_data = client.get(f"/lots/{lot_id}", headers=farmer_headers).json()
    first_det = lot_data["detections"][0]

    override_payload = {
        "reason": "Expert reassessment found black mold rot (min 10 chars)",
        "detection_overrides": [{"detection_id": first_det["id"], "new_class": "rotten"}],
    }
    ovr_resp = client.post(f"/lots/{lot_id}/override", json=override_payload, headers=staff_headers)
    assert ovr_resp.status_code == 200

    # 3. Generate Report v2 (POST /lots/{id}/report)
    rep2_resp = client.post(f"/lots/{lot_id}/report", headers=staff_headers)
    assert rep2_resp.status_code == 201
    rep2_id = rep2_resp.json()["id"]
    assert rep2_resp.json()["version"] == 2

    # 4. Check Report v1: must show superseded status
    v1_check = client.get(f"/verify/{rep1_id}").json()
    assert v1_check["status"] == "SUPERSEDED"
    assert v1_check["is_superseded"] is True
    assert v1_check["superseded_by_report_id"] == rep2_id

    # 5. Check Report v2: must show valid status
    v2_check = client.get(f"/verify/{rep2_id}").json()
    assert v2_check["status"] == "VALID"
    assert v2_check["is_superseded"] is False
    assert v2_check["version"] == 2

    # 6. HTML view for Report v1 references Report v2
    html_v1 = client.get(f"/verify/{rep1_id}/view")
    assert "SUPERSEDED VERSION" in html_v1.text
    assert f"View Report #{rep2_id}" in html_v1.text
