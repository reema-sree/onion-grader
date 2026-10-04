"""
Mock inference backend for testing and development.

Returns plausible random detections.  The marker is always "detected"
in mock mode so that pipeline stage 2 doesn't block grading.
"""
import random
import numpy as np


def mock_infer(image: np.ndarray) -> dict:
    """
    Generate plausible random detections for testing.

    The marker is always considered detected (ArUco method) in mock mode
    so the full pipeline can complete without a physical printed marker.
    """
    h, w = image.shape[:2]
    random.seed(h * w)  # somewhat deterministic based on image size

    num_detections = random.randint(5, 15)
    classes = ['good', 'damaged', 'rotten', 'sprouted', 'undersized']
    weights = [0.6, 0.1, 0.1, 0.1, 0.1]

    detections = []
    for _ in range(num_detections):
        size_w = random.randint(50, 200)
        size_h = random.randint(50, 200)
        x1 = random.randint(0, max(0, w - size_w))
        y1 = random.randint(0, max(0, h - size_h))
        x2 = min(w, x1 + size_w)
        y2 = min(h, y1 + size_h)

        # Octagon approximation for mask polygon
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        rx, ry = (x2 - x1) / 2, (y2 - y1) / 2
        polygon = [
            [cx - rx, cy - 0.5 * ry], [cx - 0.5 * rx, cy - ry],
            [cx + 0.5 * rx, cy - ry], [cx + rx, cy - 0.5 * ry],
            [cx + rx, cy + 0.5 * ry], [cx + 0.5 * rx, cy + ry],
            [cx - 0.5 * rx, cy + ry], [cx - rx, cy + 0.5 * ry]
        ]

        cls = random.choices(classes, weights=weights, k=1)[0]
        conf = random.uniform(0.7, 0.99)
        diameter = random.uniform(3.0, 10.0)

        detections.append({
            'bbox': [x1, y1, x2, y2],
            'mask_polygon': polygon,
            'class': cls,
            'confidence': conf,
            'diameter_cm': diameter,
            'marker_status': 'detected',
            'mock': True,
        })

    # Mock marker always detected (ArUco-compatible fields)
    marker_pixels_per_cm = random.uniform(30.0, 50.0)

    return {
        'detections': detections,
        'marker_status': 'detected',
        'marker_method': 'aruco',
        'marker_id': 0,
        'marker_pixels_per_cm': marker_pixels_per_cm,
        'total_detections': len(detections),
        'mock': True,
    }
