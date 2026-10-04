"""
ArUco reference marker detection for physical-size calibration.

Primary: OpenCV ArUco DICT_4X4_50 marker (ID 0, default 5 cm side length).
Fallback: HoughCircles (coin detection) — low-confidence, optional.

The marker is designed to be printed at exactly the configured size using
/ml/make_marker.py.  Users MUST print at 100 % scale (no "fit to page").
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# ArUco dictionary used throughout the whole project
# ---------------------------------------------------------------------------
ARUCO_DICT_ID = cv2.aruco.DICT_4X4_50
ARUCO_MARKER_ID = 0  # We always generate / detect marker ID 0


class MarkerStatus(str, Enum):
    DETECTED = "detected"
    FALLBACK = "fallback"   # coin / HoughCircles used
    NOT_FOUND = "not_found"
    LOW_CONFIDENCE = "low_confidence"


def _get_aruco_detector():
    """Return a configured ArUco detector (works across OpenCV 4.x and 4.8+)."""
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_ID)
    params = cv2.aruco.DetectorParameters()
    # Relax corner refinement for printed markers under varied lighting
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(dictionary, params)


def detect_aruco(
    image: np.ndarray,
    marker_side_cm: float = 5.0,
    target_id: int = ARUCO_MARKER_ID,
) -> Dict:
    """
    Detect the printed ArUco marker in *image*.

    Returns
    -------
    {
        "detected": bool,
        "method": "aruco" | "coin_fallback" | "none",
        "status": MarkerStatus,
        "bbox": [x1, y1, x2, y2] | None,
        "corners": list[list[float]] | None,   # 4 corners in order
        "pixels_per_cm": float | None,
        "confidence": float,
        "marker_id": int | None,
    }
    """
    result: Dict = {
        "detected": False,
        "method": "none",
        "status": MarkerStatus.NOT_FOUND,
        "bbox": None,
        "corners": None,
        "pixels_per_cm": None,
        "confidence": 0.0,
        "marker_id": None,
    }

    # ------------------------------------------------------------------
    # 1. ArUco detection (primary)
    # ------------------------------------------------------------------
    try:
        detector = _get_aruco_detector()
        corners_list, ids, _ = detector.detectMarkers(image)

        if ids is not None and len(ids) > 0:
            # Prefer the target ID; otherwise take the first detected marker
            matched_idx = None
            for i, mid in enumerate(ids.flatten()):
                if mid == target_id:
                    matched_idx = i
                    break
            if matched_idx is None:
                matched_idx = 0  # use whatever was found

            corners = corners_list[matched_idx][0]  # shape (4, 2)
            marker_id = int(ids.flatten()[matched_idx])

            # Axis-aligned bounding box
            x1, y1 = corners.min(axis=0)
            x2, y2 = corners.max(axis=0)

            # Side length in pixels (average of all four sides)
            side_px = float(np.mean([
                np.linalg.norm(corners[1] - corners[0]),
                np.linalg.norm(corners[2] - corners[1]),
                np.linalg.norm(corners[3] - corners[2]),
                np.linalg.norm(corners[0] - corners[3]),
            ]))
            pixels_per_cm = side_px / marker_side_cm

            result.update({
                "detected": True,
                "method": "aruco",
                "status": MarkerStatus.DETECTED,
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "corners": corners.tolist(),
                "pixels_per_cm": pixels_per_cm,
                "confidence": 0.99,
                "marker_id": marker_id,
            })
            return result

    except Exception as exc:  # pragma: no cover – OpenCV version differences
        pass

    # ------------------------------------------------------------------
    # 2. Coin / HoughCircles fallback (optional, low confidence)
    # ------------------------------------------------------------------
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)

    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
        param1=50, param2=30, minRadius=10, maxRadius=200,
    )

    if circles is not None:
        circles = np.uint16(np.around(circles))
        cx, cy, r = circles[0, 0]
        cx, cy, r = int(cx), int(cy), int(r)
        # Treat the coin diameter as marker_side_cm (user-configured coin size)
        pixels_per_cm = (2 * r) / marker_side_cm
        result.update({
            "detected": True,
            "method": "coin_fallback",
            "status": MarkerStatus.FALLBACK,
            "bbox": [cx - r, cy - r, cx + r, cy + r],
            "pixels_per_cm": pixels_per_cm,
            "confidence": 0.45,
            "marker_id": None,
        })

    return result


def calibrate_detections_with_aruco(
    detections: List[Dict],
    marker_result: Dict,
    fallback_pixels_per_cm: Optional[float] = None,
) -> List[Dict]:
    """
    Add *diameter_cm* to each detection dict using the marker calibration.

    If the marker was not found and no fallback is supplied, diameter_cm is None.
    """
    ppc: Optional[float] = marker_result.get("pixels_per_cm") or fallback_pixels_per_cm
    status_str: str = marker_result.get("status", MarkerStatus.NOT_FOUND).value if isinstance(
        marker_result.get("status"), MarkerStatus
    ) else str(marker_result.get("status", MarkerStatus.NOT_FOUND.value))

    updated: List[Dict] = []
    for det in detections:
        new_det = det.copy()
        if ppc and ppc > 0:
            bbox = det.get("bbox") or []
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                max_dim = max(x2 - x1, y2 - y1)
                new_det["diameter_cm"] = float(max_dim / ppc)
            else:
                new_det["diameter_cm"] = None
        else:
            new_det["diameter_cm"] = None

        new_det["marker_status"] = status_str
        updated.append(new_det)

    return updated
