"""
Main inference interface for the onion grading pipeline.
"""
import os
import numpy as np

from .mock_backend import mock_infer
from .real_backend import real_infer


def infer(image: np.ndarray) -> dict:
    """
    Run inference on a single image.
    
    Returns:
        {
            'detections': [
                {
                    'bbox': [x1, y1, x2, y2],
                    'mask_polygon': [[x,y], ...],
                    'class': 'good' | 'damaged' | 'rotten' | 'sprouted' | 'undersized',
                    'confidence': float,
                    'diameter_cm': float | None,
                    'mock': bool  # True only when MOCK_MODEL is active
                },
                ...
            ],
            'marker_status': 'detected' | 'not_found' | 'low_confidence',
            'marker_pixels_per_cm': float | None,
            'total_detections': int,
            'mock': bool  # True when MOCK_MODEL is active
        }
    """
    is_mock = os.getenv('MOCK_MODEL', 'false').lower() in ('true', '1', 'yes')
    if is_mock:
        return mock_infer(image)
    else:
        return real_infer(image)
