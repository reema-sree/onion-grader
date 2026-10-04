"""Unit tests for capture quality checks and retake error messages."""

import io
import cv2
import numpy as np
import pytest

from backend.app.services.quality import (
    QualityCheckError,
    check_image_blur,
    check_overlapping_boxes,
    validate_inference_quality,
)


def test_upload_invalid_file_type(client, farmer_headers, seed_centre):
    """Uploading a non-image file returns 400 Bad Request."""
    lot = client.post("/lots", json={"farmer_name": "Test", "centre_id": seed_centre.id}, headers=farmer_headers).json()
    files = [("files", ("test.txt", io.BytesIO(b"hello world"), "text/plain"))]
    resp = client.post(f"/lots/{lot['id']}/images", files=files, headers=farmer_headers)
    assert resp.status_code == 400
    assert "Invalid file type" in resp.json()["detail"]


def test_upload_exceeds_max_images(client, farmer_headers, seed_centre):
    """Uploading more than 3 images in total returns 400 Bad Request."""
    lot = client.post("/lots", json={"farmer_name": "Test", "centre_id": seed_centre.id}, headers=farmer_headers).json()

    img = np.ones((100, 100, 3), dtype=np.uint8) * 128
    _, buf = cv2.imencode(".jpg", img)
    raw = buf.tobytes()

    files = [
        ("files", ("img1.jpg", io.BytesIO(raw), "image/jpeg")),
        ("files", ("img2.jpg", io.BytesIO(raw), "image/jpeg")),
        ("files", ("img3.jpg", io.BytesIO(raw), "image/jpeg")),
        ("files", ("img4.jpg", io.BytesIO(raw), "image/jpeg")),
    ]
    resp = client.post(f"/lots/{lot['id']}/images", files=files, headers=farmer_headers)
    assert resp.status_code == 400
    assert "at most 3 images" in resp.json()["detail"]


def test_grade_lot_without_images(client, farmer_headers, seed_centre):
    """Triggering grading on a lot with 0 images returns 400 Bad Request."""
    lot = client.post("/lots", json={"farmer_name": "Test", "centre_id": seed_centre.id}, headers=farmer_headers).json()
    resp = client.post(f"/lots/{lot['id']}/grade", headers=farmer_headers)
    assert resp.status_code == 400
    assert "No images uploaded" in resp.json()["detail"]


def test_quality_blur_error_guidance():
    """A blurry image triggers IMAGE_TOO_BLURRY with clear retake guidance."""
    # A completely solid uniform image has 0 variance (extremely blurry)
    blurry_img = np.ones((480, 640, 3), dtype=np.uint8) * 100
    is_blurry, var = check_image_blur(blurry_img, threshold=40.0)
    assert is_blurry is True

    inference_res = {
        "mock": False,
        "detections": [{"bbox": [10, 10, 50, 50], "class": "good"}],
        "marker_status": "detected"
    }
    with pytest.raises(QualityCheckError) as exc_info:
        validate_inference_quality(blurry_img, inference_res, allow_mock_bypass=False)

    assert exc_info.value.error_code == "IMAGE_TOO_BLURRY"
    assert "blurry" in exc_info.value.message.lower()
    assert "hold the camera steady" in exc_info.value.guidance.lower()


def test_quality_no_onions_found_error_guidance():
    """Inference detecting 0 onions triggers NO_ONIONS_FOUND with retake guidance."""
    sharp_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    inference_res = {
        "mock": False,
        "detections": [],
        "marker_status": "detected"
    }
    with pytest.raises(QualityCheckError) as exc_info:
        validate_inference_quality(sharp_img, inference_res, allow_mock_bypass=False)

    assert exc_info.value.error_code == "NO_ONIONS_FOUND"
    assert "place onions clearly" in exc_info.value.guidance.lower()


def test_quality_marker_not_found_error_guidance():
    """Inference missing calibration marker triggers MARKER_NOT_FOUND with retake guidance."""
    sharp_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    inference_res = {
        "mock": False,
        "detections": [{"bbox": [50, 50, 150, 150], "class": "good"}],
        "marker_status": "not_found"
    }
    with pytest.raises(QualityCheckError) as exc_info:
        validate_inference_quality(sharp_img, inference_res, allow_mock_bypass=False)

    assert exc_info.value.error_code == "MARKER_NOT_FOUND"
    assert "coin" in exc_info.value.guidance.lower() or "card" in exc_info.value.guidance.lower()


def test_quality_overlapping_onions_error_guidance():
    """Heavily overlapping detections trigger TOO_MANY_OVERLAPPING_ONIONS with guidance."""
    # Boxes with almost 100% overlap
    boxes = [
        [100, 100, 200, 200],
        [105, 105, 205, 205],
        [102, 102, 202, 202],
    ]
    is_overlapping, ratio = check_overlapping_boxes(boxes, iou_threshold=0.45, max_overlap_ratio=0.30)
    assert is_overlapping is True

    sharp_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    inference_res = {
        "mock": False,
        "detections": [{"bbox": b, "class": "good"} for b in boxes],
        "marker_status": "detected"
    }
    with pytest.raises(QualityCheckError) as exc_info:
        validate_inference_quality(sharp_img, inference_res, allow_mock_bypass=False)

    assert exc_info.value.error_code == "TOO_MANY_OVERLAPPING_ONIONS"
    assert "spread the onions out" in exc_info.value.guidance.lower()
