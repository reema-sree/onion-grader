"""
Tests for mock inference backend.
"""
import os
import pytest
import numpy as np

from ml.inference.mock_backend import mock_infer
from ml.inference.interface import infer


@pytest.fixture
def dummy_image():
    """Returns a dummy 640x480x3 image for testing."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_mock_returns_detections(dummy_image):
    result = mock_infer(dummy_image)
    assert 'detections' in result
    assert isinstance(result['detections'], list)
    assert 'marker_status' in result
    assert 'marker_pixels_per_cm' in result
    assert 'total_detections' in result
    assert 'mock' in result


def test_mock_flag_on_all_detections(dummy_image):
    result = mock_infer(dummy_image)
    for det in result['detections']:
        assert det.get('mock') is True


def test_mock_top_level_flag(dummy_image):
    result = mock_infer(dummy_image)
    assert result.get('mock') is True


def test_mock_classes_valid(dummy_image):
    valid_classes = {'good', 'damaged', 'rotten', 'sprouted', 'undersized'}
    result = mock_infer(dummy_image)
    for det in result['detections']:
        assert det['class'] in valid_classes


def test_mock_confidence_range(dummy_image):
    result = mock_infer(dummy_image)
    for det in result['detections']:
        assert 0.0 <= det['confidence'] <= 1.0


def test_mock_diameter_range(dummy_image):
    result = mock_infer(dummy_image)
    for det in result['detections']:
        diam = det['diameter_cm']
        assert 1.0 <= diam <= 15.0


def test_mock_detection_count(dummy_image):
    result = mock_infer(dummy_image)
    count = len(result['detections'])
    assert 5 <= count <= 15
    assert result['total_detections'] == count


def test_mock_marker_status(dummy_image):
    result = mock_infer(dummy_image)
    assert result['marker_status'] in {'detected', 'not_found', 'low_confidence'}
    if result['marker_status'] == 'detected':
        assert result['marker_pixels_per_cm'] is not None


def test_infer_uses_mock_when_env_set(dummy_image, monkeypatch):
    monkeypatch.setenv('MOCK_MODEL', 'true')
    result = infer(dummy_image)
    assert result.get('mock') is True
