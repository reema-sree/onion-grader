"""
Marker calibration module.
Detects reference markers and computes pixels-per-cm ratios for size estimation.
"""
from enum import Enum
from typing import Dict, List, Optional, Union
import numpy as np
import cv2


class MarkerStatus(str, Enum):
    """Status of marker detection."""
    DETECTED = "detected"
    NOT_FOUND = "not_found"
    LOW_CONFIDENCE = "low_confidence"


class MarkerCalibrator:
    """
    Calibrates image dimensions using a reference marker of known size.
    """

    def __init__(self, known_marker_size_cm: float = 2.5):
        """
        Initialize the calibrator.
        
        Args:
            known_marker_size_cm: The real-world size of the marker in cm.
        """
        self.known_marker_size_cm = known_marker_size_cm

    def detect_marker(self, image: np.ndarray, marker_bbox: Optional[Dict] = None) -> Dict:
        """
        Detect a marker in the image or use the provided bbox.
        
        Args:
            image: The image as a numpy array.
            marker_bbox: Optional dict with 'bbox' key [x1, y1, x2, y2].
            
        Returns:
            Dict containing detection status, bbox, pixels_per_cm, and confidence.
        """
        result = {
            "detected": False,
            "bbox": None,
            "pixels_per_cm": None,
            "confidence": 0.0,
            "status": MarkerStatus.NOT_FOUND.value
        }

        if marker_bbox and "bbox" in marker_bbox:
            bbox = marker_bbox["bbox"]
            result["detected"] = True
            result["bbox"] = bbox
            result["pixels_per_cm"] = self.compute_pixels_per_cm(bbox)
            result["confidence"] = marker_bbox.get("confidence", 1.0)
            result["status"] = MarkerStatus.DETECTED.value
            return result

        # Fallback: attempt to detect circular markers using HoughCircles
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
            param1=50, param2=30, minRadius=10, maxRadius=200
        )
        
        if circles is not None:
            circles = np.uint16(np.around(circles))
            # Take the most prominent circle (first one)
            i = circles[0, 0]
            x, y, r = int(i[0]), int(i[1]), int(i[2])
            
            bbox = [x - r, y - r, x + r, y + r]
            result["detected"] = True
            result["bbox"] = bbox
            result["pixels_per_cm"] = self.compute_pixels_per_cm(bbox)
            result["confidence"] = 0.5  # Lower confidence for fallback detection
            result["status"] = MarkerStatus.DETECTED.value
            
        return result

    def compute_pixels_per_cm(self, marker_bbox: List[float]) -> float:
        """
        Compute the pixels per cm ratio from a marker bounding box.
        
        Args:
            marker_bbox: [x1, y1, x2, y2] bounding box of the marker.
            
        Returns:
            The pixels per cm ratio.
        """
        x1, y1, x2, y2 = marker_bbox
        width = x2 - x1
        height = y2 - y1
        max_dim = max(width, height)
        return float(max_dim / self.known_marker_size_cm)

    def estimate_diameter_cm(self, mask_or_bbox: Dict, pixels_per_cm: float) -> float:
        """
        Estimate the real-world diameter in cm from a bbox or mask polygon.
        
        Args:
            mask_or_bbox: Dict containing either 'bbox' [x1, y1, x2, y2] or 'polygon' (list of [x, y]).
            pixels_per_cm: The pixels per cm ratio.
            
        Returns:
            The estimated diameter in cm.
        """
        if "polygon" in mask_or_bbox:
            polygon = np.array(mask_or_bbox["polygon"])
            x, y, w, h = cv2.boundingRect(np.float32(polygon))
            max_dim = max(w, h)
        elif "bbox" in mask_or_bbox:
            x1, y1, x2, y2 = mask_or_bbox["bbox"]
            max_dim = max(x2 - x1, y2 - y1)
        else:
            raise ValueError("mask_or_bbox must contain either 'bbox' or 'polygon'")
            
        return float(max_dim / pixels_per_cm)

    def calibrate_detections(self, detections: List[Dict], marker_detection: Optional[Dict]) -> List[Dict]:
        """
        Add diameter_cm to each detection based on the marker.
        
        Args:
            detections: List of detection dicts (must have 'bbox' or 'polygon').
            marker_detection: Dict of marker detection or None.
            
        Returns:
            List of updated detection dicts.
        """
        updated_detections = []
        
        if marker_detection and marker_detection.get("detected"):
            pixels_per_cm = marker_detection["pixels_per_cm"]
            status = MarkerStatus.DETECTED.value
        else:
            pixels_per_cm = None
            status = MarkerStatus.NOT_FOUND.value
            
        for det in detections:
            new_det = det.copy()
            if pixels_per_cm is not None:
                new_det["diameter_cm"] = self.estimate_diameter_cm(det, pixels_per_cm)
            else:
                new_det["diameter_cm"] = None
                
            new_det["marker_status"] = status
            updated_detections.append(new_det)
            
        return updated_detections
