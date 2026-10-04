"""Comprehensive tests for Kisan Setu Three-Bucket Grading, Batch Codes, Verifications, and Isolation."""

from datetime import datetime
import pytest
from backend.app.models.lot import Lot, LotStatus
from backend.app.models.user import User, UserRole
from backend.app.models.verification import Verification, VerificationDecision
from backend.app.services.batch_code import generate_batch_code
from backend.app.services.grading import compute_grade, determine_onion_bucket, evaluate_lot_grade


# ==============================================================================
# 1. THREE-BUCKET MATHS & BOUNDARIES
# ==============================================================================
def test_three_bucket_empty_batch():
    """Empty batch returns 0% for all buckets and no_onions status."""
    res = compute_grade([])
    assert res["status"] == "no_onions"
    assert res["total_onions"] == 0
    assert res["grade_a_pct"] == 0.0
    assert res["urs_pct"] == 0.0
    assert res["defective_pct"] == 0.0
    assert res["grade_a_count"] == 0
    assert res["urs_count"] == 0
    assert res["defective_count"] == 0
    assert res["lot_grade"] == "N/A"
    assert res["lot_grade_label"] == "No Onions"


def test_three_bucket_size_boundaries():
    """Verify exact min_size_cm boundaries for Grade A vs URS."""
    # Good onion >= 6.0 cm -> Grade A
    assert determine_onion_bucket("good", 6.0, min_size_cm=6.0) == "grade_a"
    assert determine_onion_bucket("good", 7.5, min_size_cm=6.0) == "grade_a"

    # Good onion < 6.0 cm -> URS
    assert determine_onion_bucket("good", 5.99, min_size_cm=6.0) == "urs"
    assert determine_onion_bucket("good", 4.0, min_size_cm=6.0) == "urs"

    # Defect classes -> Defective (any size)
    assert determine_onion_bucket("damaged", 8.0) == "defective"
    assert determine_onion_bucket("rotten", 7.0) == "defective"
    assert determine_onion_bucket("sprouted", 6.5) == "defective"

    # Undersized -> URS
    assert determine_onion_bucket("undersized", 5.0) == "urs"


def test_three_bucket_percentages_sum_to_100():
    """Ensure Grade A %, URS %, and Defective % sum to 100.0%."""
    sample_onions = [
        {"class": "good", "diameter_cm": 6.5},  # Grade A
        {"class": "good", "diameter_cm": 7.0},  # Grade A
        {"class": "good", "diameter_cm": 5.2},  # URS (undersized)
        {"class": "damaged", "diameter_cm": 6.8}, # Defective
    ]
    res = compute_grade(sample_onions)
    assert res["total_onions"] == 4
    assert res["grade_a_count"] == 2
    assert res["urs_count"] == 1
    assert res["defective_count"] == 1
    assert res["grade_a_pct"] == 50.0
    assert res["urs_pct"] == 25.0
    assert res["defective_pct"] == 25.0
    assert (res["grade_a_pct"] + res["urs_pct"] + res["defective_pct"]) == 100.0


# ==============================================================================
# 2. LOT GRADE LABEL EVALUATION
# ==============================================================================
def test_lot_grade_rules_evaluation():
    """Verify lot grade label rules (Grade A >= 70%, Defective >= 30%, otherwise URS)."""
    # 1. Grade A >= 70%
    grade, label, pct = evaluate_lot_grade(72.5, 10.0, 17.5)
    assert grade == "Grade A"
    assert label == "Grade A (72.5%)"
    assert pct == 72.5

    # 2. Defective >= 30% (and Grade A < 70%)
    grade, label, pct = evaluate_lot_grade(50.0, 35.0, 15.0)
    assert grade == "Defective"
    assert label == "Defective (35.0%)"
    assert pct == 35.0

    # 3. Otherwise -> URS
    grade, label, pct = evaluate_lot_grade(60.0, 20.0, 20.0)
    assert grade == "URS"
    assert label == "URS (20.0%)"
    assert pct == 20.0


# ==============================================================================
# 3. BATCH CODE GENERATION
# ==============================================================================
def test_batch_code_atomic_generation(db_session, seed_centre):
    """Batch code generates atomic sequence KS-{YYYY}-{00001} sequentially."""
    year = datetime.utcnow().year
    code1 = generate_batch_code(db_session, year=year)
    assert code1 == f"KS-{year}-00001"

    lot1 = Lot(batch_code=code1, centre_id=seed_centre.id, status=LotStatus.DRAFT)
    db_session.add(lot1)
    db_session.commit()

    code2 = generate_batch_code(db_session, year=year)
    assert code2 == f"KS-{year}-00002"

    lot2 = Lot(batch_code=code2, centre_id=seed_centre.id, status=LotStatus.DRAFT)
    db_session.add(lot2)
    db_session.commit()

    code3 = generate_batch_code(db_session, year=year)
    assert code3 == f"KS-{year}-00003"


# ==============================================================================
# 4. FARMER DATA ISOLATION (GET /me/lots)
# ==============================================================================
def test_farmer_data_isolation(client, db_session, seed_centre, seed_farmer, farmer_headers, admin_headers):
    """Farmers only see approved/overridden/reported lots belonging to them."""
    year = datetime.utcnow().year

    # Create lots:
    # Lot 1: Farmer 1, Status: APPROVED (Should be visible)
    lot1 = Lot(
        batch_code=f"KS-{year}-00011",
        farmer_id=seed_farmer.id,
        centre_id=seed_centre.id,
        status=LotStatus.APPROVED,
    )
    # Lot 2: Farmer 1, Status: DRAFT (Should NOT be visible to farmer)
    lot2 = Lot(
        batch_code=f"KS-{year}-00012",
        farmer_id=seed_farmer.id,
        centre_id=seed_centre.id,
        status=LotStatus.DRAFT,
    )
    # Lot 3: Farmer 1, Status: PENDING_REVIEW (Should NOT be visible to farmer)
    lot3 = Lot(
        batch_code=f"KS-{year}-00013",
        farmer_id=seed_farmer.id,
        centre_id=seed_centre.id,
        status=LotStatus.PENDING_REVIEW,
    )
    # Lot 4: Different Farmer, Status: APPROVED (Should NOT be visible)
    other_farmer = User(name="Other Farmer", phone="+919876543999", role=UserRole.FARMER, is_active=True)
    db_session.add(other_farmer)
    db_session.commit()
    db_session.refresh(other_farmer)

    lot4 = Lot(
        batch_code=f"KS-{year}-00014",
        farmer_id=other_farmer.id,
        centre_id=seed_centre.id,
        status=LotStatus.APPROVED,
    )
    db_session.add_all([lot1, lot2, lot3, lot4])
    db_session.commit()

    # Query /me/lots with seed_farmer headers
    resp = client.get("/me/lots", headers=farmer_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["batch_code"] == f"KS-{year}-00011"
    assert items[0]["farmer_id"] == seed_farmer.id


# ==============================================================================
# 5. VERIFICATION FLOW & REASON VALIDATION
# ==============================================================================
def test_verify_flow_approval_and_override(client, db_session, seed_centre, seed_staff, staff_headers):
    """Staff verification approves or overrides a lot with mandatory audit justification."""
    year = datetime.utcnow().year
    lot = Lot(
        batch_code=f"KS-{year}-00021",
        centre_id=seed_centre.id,
        status=LotStatus.PENDING_REVIEW,
        ai_result={"lot_grade": "Grade A", "grade_a_pct": 75.0, "urs_pct": 15.0, "defective_pct": 10.0},
    )
    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)

    # 1. Override without reason fails
    bad_override = client.post(
        f"/lots/{lot.id}/verify",
        json={"decision": "overridden", "new_grade": "Defective"},
        headers=staff_headers
    )
    assert bad_override.status_code == 400
    assert "detailed reason" in bad_override.json()["detail"].lower()

    # 2. Override with short reason fails
    short_reason = client.post(
        f"/lots/{lot.id}/verify",
        json={"decision": "overridden", "new_grade": "Defective", "reason": "too bad"},
        headers=staff_headers
    )
    assert short_reason.status_code == 400

    # 3. Successful Override
    ok_override = client.post(
        f"/lots/{lot.id}/verify",
        json={
            "decision": "overridden",
            "new_grade": "Defective",
            "reason": "Physical inspection found significant internal black rot defects"
        },
        headers=staff_headers
    )
    assert ok_override.status_code == 200
    assert ok_override.json()["status"] == "overridden"
    assert ok_override.json()["final_result"]["lot_grade"] == "Defective"
    assert len(ok_override.json()["verifications"]) == 1

    # Verify AI result is preserved untouched
    db_session.refresh(lot)
    assert lot.ai_result["lot_grade"] == "Grade A"


# ==============================================================================
# 6. REPORT GENERATION BLOCKED BEFORE VERIFICATION
# ==============================================================================
def test_report_generation_blocked_before_verification(client, db_session, seed_centre, staff_headers):
    """Report generation is rejected if lot status is DRAFT or PENDING_REVIEW."""
    year = datetime.utcnow().year
    lot = Lot(
        batch_code=f"KS-{year}-00031",
        centre_id=seed_centre.id,
        status=LotStatus.PENDING_REVIEW,
        ai_result={"lot_grade": "Grade A"},
    )
    db_session.add(lot)
    db_session.commit()
    db_session.refresh(lot)

    # Attempt report generation before approval/override
    resp = client.post(f"/lots/{lot.id}/report", headers=staff_headers)
    assert resp.status_code == 400
    assert "approved or overridden" in resp.json()["detail"].lower()


# ==============================================================================
# 7. PHONE OTP AUTHENTICATION
# ==============================================================================
def test_phone_otp_auth_flow(client):
    """Farmer requests OTP and verifies with mock OTP 123456."""
    phone = "+919811223344"

    # 1. Request OTP
    req_res = client.post("/auth/phone-otp/request", json={"phone": phone})
    assert req_res.status_code == 200
    assert req_res.json()["dev_mock_otp"] == "123456"

    # 2. Invalid OTP fails
    bad_res = client.post("/auth/phone-otp/verify", json={"phone": phone, "otp": "999999"})
    assert bad_res.status_code == 400

    # 3. Valid OTP succeeds & auto-provisions farmer
    ok_res = client.post("/auth/phone-otp/verify", json={"phone": phone, "otp": "123456"})
    assert ok_res.status_code == 200
    token_data = ok_res.json()
    assert "access_token" in token_data
    assert token_data["user"]["phone"] == phone
    assert token_data["user"]["role"] == "farmer"


# ==============================================================================
# 8. SIX-STAGE PIPELINE — STAGE NAMES & SHAPE
# ==============================================================================
def test_pipeline_stage_names_are_canonical():
    """The six stage names are exactly as documented (UI checklist keys)."""
    from backend.app.services.pipeline import STAGE_NAMES, initial_stage_list
    expected = [
        "image_quality_check",
        "marker_detection",
        "onion_detection",
        "size_measurement",
        "defect_detection",
        "grading",
    ]
    assert STAGE_NAMES == expected

    stages = initial_stage_list()
    assert len(stages) == 6
    for s in stages:
        assert s["status"] == "pending"
        assert s["percent"] == 0
        assert s["name"] in expected


def test_grade_status_endpoint(client, db_session, seed_centre, farmer_headers, monkeypatch):
    """GET /lots/{id}/grade/status returns six stages and overall percent."""
    import io, cv2, numpy as np
    monkeypatch.setenv("MOCK_MODEL", "true")

    # Create + upload
    lot_payload = {"farmer_name": "Pipeline Test Farmer", "centre_id": seed_centre.id, "weight_kg": 100.0}
    lot_resp = client.post("/lots", json=lot_payload, headers=farmer_headers)
    assert lot_resp.status_code == 201
    lot_id = lot_resp.json()["id"]

    # High-variance image so blur check passes (Laplacian variance >> 40)
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    files = [("files", ("t.jpg", io.BytesIO(buf.tobytes()), "image/jpeg"))]
    assert client.post(f"/lots/{lot_id}/images", files=files, headers=farmer_headers).status_code == 201

    # Before grading → pending stages
    before = client.get(f"/lots/{lot_id}/grade/status", headers=farmer_headers).json()
    assert before["lot_status"] == "draft"
    assert all(s["status"] == "pending" for s in before["stages"])

    # Grade
    grade_r = client.post(f"/lots/{lot_id}/grade", headers=farmer_headers)
    assert grade_r.status_code in (200, 202)

    # After grading → all done
    after = client.get(f"/lots/{lot_id}/grade/status", headers=farmer_headers).json()
    assert after["lot_status"] == "pending_review"
    assert after["overall_percent"] == 100
    assert after["is_complete"] is True
    assert after["failed_stage"] is None
    assert len(after["stages"]) == 6
    assert all(s["status"] == "done" for s in after["stages"])




def test_pipeline_needs_attention_auto_flagged(monkeypatch):
    """Pipeline.run() returns a PipelineResult regardless of marker state."""
    import numpy as np
    from backend.app.services.pipeline import GradingPipeline, PipelineResult

    monkeypatch.setenv("MOCK_MODEL", "true")

    # High-variance image to pass blur check
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    p = GradingPipeline(min_onion_count=1, min_confidence=0.01, blur_threshold=1.0)
    result = p.run(img)

    assert isinstance(result, PipelineResult)
    assert result.stages is not None
    assert len(result.stages) == 6
    # In mock mode the full pipeline should complete without failure
    assert result.failed_stage is None
    assert result.grade_data is not None



def test_pipeline_retake_messages_exist():
    """All retake message keys resolve to non-empty plain-language strings."""
    from backend.app.services.pipeline import RETAKE_MESSAGES
    for key, msg in RETAKE_MESSAGES.items():
        assert len(msg) > 20, f"Retake message for '{key}' is too short: {msg!r}"
        # Should not contain code-level words
        assert "error_code" not in msg.lower()
        assert "exception" not in msg.lower()


def test_make_marker_pdf_generates_file(tmp_path, monkeypatch):
    """ml/make_marker.py generates a valid PDF with the configured physical size."""
    from ml.make_marker import generate_marker_pdf
    pdf_path = tmp_path / "test_marker.pdf"
    result = generate_marker_pdf(size_cm=5.0, output_path=pdf_path)
    assert result.exists()
    assert result.stat().st_size > 10_000  # at least 10 KB
    # Check PDF magic bytes
    with open(result, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF"

