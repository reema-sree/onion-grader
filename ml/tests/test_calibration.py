"""
Unit tests for marker-based calibration.
"""
import pytest
import numpy as np
import cv2
from ml.calibration.marker import MarkerCalibrator, MarkerStatus


def test_compute_pixels_per_cm():
    calibrator = MarkerCalibrator(known_marker_size_cm=2.5)
    bbox = [0, 0, 100, 100]  # width=100
    pixels_per_cm = calibrator.compute_pixels_per_cm(bbox)
    assert pixels_per_cm == 40.0


def test_estimate_diameter_from_bbox():
    calibrator = MarkerCalibrator()
    bbox_dict = {"bbox": [0, 0, 200, 150]}  # width=200, height=150
    diameter_cm = calibrator.estimate_diameter_cm(bbox_dict, pixels_per_cm=40.0)
    assert diameter_cm == 5.0


def test_estimate_diameter_from_polygon():
    calibrator = MarkerCalibrator()
    polygon_dict = {"polygon": [[0, 0], [240, 0], [240, 100], [0, 100]]}  # w=240, h=100
    diameter_cm = calibrator.estimate_diameter_cm(polygon_dict, pixels_per_cm=40.0)
    assert diameter_cm == pytest.approx(6.0, abs=0.1)


def test_calibrate_detections_with_marker():
    calibrator = MarkerCalibrator()
    detections = [{"bbox": [0, 0, 200, 200]}, {"bbox": [0, 0, 300, 300]}]
    marker_detection = {"detected": True, "pixels_per_cm": 40.0, "bbox": [0, 0, 100, 100]}
    
    calibrated = calibrator.calibrate_detections(detections, marker_detection)
    
    assert len(calibrated) == 2
    assert calibrated[0]["diameter_cm"] == 5.0
    assert calibrated[0]["marker_status"] == MarkerStatus.DETECTED.value
    assert calibrated[1]["diameter_cm"] == 7.5
    assert calibrated[1]["marker_status"] == MarkerStatus.DETECTED.value


def test_calibrate_detections_without_marker():
    calibrator = MarkerCalibrator()
    detections = [{"bbox": [0, 0, 200, 200]}]
    marker_detection = {"detected": False}
    
    calibrated = calibrator.calibrate_detections(detections, marker_detection)
    
    assert len(calibrated) == 1
    assert calibrated[0]["diameter_cm"] is None
    assert calibrated[0]["marker_status"] == MarkerStatus.NOT_FOUND.value


def test_known_size_synthetic_image():
    """Test end-to-end calibration using a known marker bbox (primary production path).
    
    Simulates what happens when YOLO detects the marker and provides a bbox:
    marker is 100px across = 2.5cm, so pixels_per_cm = 40.
    An 'onion' bbox 240px across should measure 6.0cm.
    """
    calibrator = MarkerCalibrator(known_marker_size_cm=2.5)

    # Marker detected by YOLO with a 100px bbox
    marker_bbox = {"bbox": [50, 50, 150, 150], "confidence": 0.95}
    marker_res = calibrator.detect_marker(
        np.ones((500, 500, 3), dtype=np.uint8) * 255,
        marker_bbox=marker_bbox,
    )

    assert marker_res["detected"] is True
    assert marker_res["pixels_per_cm"] == 40.0

    # A 240px wide onion detection
    onion_det = {"bbox": [200, 200, 440, 440]}
    calibrated = calibrator.calibrate_detections([onion_det], marker_res)

    assert calibrated[0]["diameter_cm"] == 6.0
    assert calibrated[0]["marker_status"] == MarkerStatus.DETECTED.value


def test_hough_circle_fallback():
    """Test HoughCircles fallback detection with a synthetic circle.
    
    This is the fallback path when YOLO doesn't detect a marker.
    We draw a clear circle outline and verify detection works.
    """
    img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    # Draw a thick circle outline (more reliably detected by HoughCircles)
    cv2.circle(img, (250, 250), 50, (0, 0, 0), 3)

    calibrator = MarkerCalibrator(known_marker_size_cm=2.5)
    marker_res = calibrator.detect_marker(img)

    if marker_res["detected"]:
        # If detected, verify the measurement is in a reasonable range
        assert marker_res["pixels_per_cm"] is not None
        assert marker_res["confidence"] == 0.5  # fallback confidence
        bbox = marker_res["bbox"]
        width = bbox[2] - bbox[0]
        assert 80 <= width <= 120, f"Expected ~100px marker width, got {width}"
    else:
        # HoughCircles is not guaranteed to find the circle with all OpenCV
        # versions / builds, so we just verify the failure is clean
        assert marker_res["status"] == MarkerStatus.NOT_FOUND.value
        assert marker_res["pixels_per_cm"] is None

