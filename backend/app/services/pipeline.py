"""
Six-stage inference pipeline with per-stage progress tracking.

Stage names (identical on server and on-device — the UI renders them as a checklist):
  1. image_quality_check
  2. marker_detection
  3. onion_detection
  4. size_measurement
  5. defect_detection
  6. grading

Each stage carries: status (pending|running|done|failed), message, and an
overall pipeline percent (0-100) that advances monotonically.

Usage (server-side)
-------------------
    pipeline = GradingPipeline(config)
    result = pipeline.run(image_bgr, lot_id=lot.id, db=db)
    # result.stages  → list[StageResult]
    # result.grade_data → dict from compute_grade()
    # result.detections → list[dict]
    # result.marker_info → dict
    # result.failed_stage → str | None
    # result.retake_message → str | None
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional

import cv2
import numpy as np

from ..core.config import settings, load_grading_rules
from ..services.grading import compute_grade
from ..services.quality import check_image_blur, check_overlapping_boxes

# ArUco marker detection (primary)
try:
    from ml.calibration.aruco_marker import detect_aruco, calibrate_detections_with_aruco
    _HAS_ARUCO = True
except ImportError:  # pragma: no cover
    _HAS_ARUCO = False

# ML inference
try:
    from ml.inference.interface import infer as ml_infer
    _HAS_INFER = True
except ImportError:  # pragma: no cover
    _HAS_INFER = False

# ────────────────────────────────────────────────────────────────────────────
# Stage constants — shared with on-device pipeline (grading_engine.js)
# ────────────────────────────────────────────────────────────────────────────
STAGE_NAMES = [
    "image_quality_check",
    "marker_detection",
    "onion_detection",
    "size_measurement",
    "defect_detection",
    "grading",
]

# Cumulative "done" percent for each stage (must be ascending, end at 100)
STAGE_DONE_PCT = {
    "image_quality_check": 10,
    "marker_detection": 25,
    "onion_detection": 50,
    "size_measurement": 65,
    "defect_detection": 82,
    "grading": 100,
}

StageStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class StageResult:
    name: str
    status: StageStatus = "pending"
    message: str = ""
    percent: int = 0

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "percent": self.percent,
        }


@dataclass
class PipelineResult:
    stages: List[StageResult] = field(default_factory=list)
    grade_data: Optional[Dict] = None
    detections: List[Dict] = field(default_factory=list)
    marker_info: Optional[Dict] = None
    is_mock: bool = False
    failed_stage: Optional[str] = None
    retake_message: Optional[str] = None
    needs_attention: bool = False
    attention_reason: Optional[str] = None

    @property
    def overall_percent(self) -> int:
        done = [s for s in self.stages if s.status == "done"]
        return done[-1].percent if done else 0

    def to_status_dict(self) -> Dict:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "overall_percent": self.overall_percent,
            "failed_stage": self.failed_stage,
            "retake_message": self.retake_message,
            "is_complete": self.failed_stage is None and self.overall_percent == 100,
            "is_mock": self.is_mock,
        }


# ────────────────────────────────────────────────────────────────────────────
# Plain-language retake instructions per failure mode
# ────────────────────────────────────────────────────────────────────────────
RETAKE_MESSAGES: Dict[str, str] = {
    "image_quality_check__blur": (
        "Image is too blurry. Hold the camera steady, ensure good lighting, "
        "and retake the photo."
    ),
    "marker_detection__not_found": (
        "Reference ArUco marker was not detected. Place the printed marker flat "
        "next to the onions, ensure it is fully visible, and retake."
    ),
    "onion_detection__none_found": (
        "No onions were detected. Place onions clearly in the centre of the frame "
        "on a plain background, and retake."
    ),
    "onion_detection__too_few": (
        "Too few onions detected for a reliable grade. Ensure all onions are visible "
        "in the frame and retake."
    ),
    "onion_detection__too_overlapping": (
        "Onions are overlapping too heavily. Spread them out on a flat surface "
        "so they do not overlap, and retake."
    ),
    "size_measurement__no_calibration": (
        "Marker detected but size measurement failed. Ensure the marker is printed "
        "at 100% scale and is fully unobstructed."
    ),
    "defect_detection__low_confidence": (
        "Detection confidence is too low for reliable grading. Improve lighting, "
        "hold the camera closer, and retake."
    ),
}


class GradingPipeline:
    """
    Server-side six-stage grading pipeline.

    Parameters
    ----------
    marker_side_cm : physical side of the ArUco marker (from grading_rules.yaml or config)
    min_onion_count : minimum detections required for grading
    min_confidence  : mean confidence threshold; below → needs_attention
    blur_threshold  : Laplacian variance below this → stage fails
    overlap_iou     : IoU threshold for "too overlapping" check
    on_stage_update : optional callback(StageResult) called after each stage
    """

    def __init__(
        self,
        marker_side_cm: float = 5.0,
        min_onion_count: int = 2,
        min_confidence: float = 0.60,
        blur_threshold: float = 40.0,
        overlap_iou: float = 0.45,
        on_stage_update: Optional[Callable[[StageResult], None]] = None,
    ):
        self.marker_side_cm = marker_side_cm
        self.min_onion_count = min_onion_count
        self.min_confidence = min_confidence
        self.blur_threshold = blur_threshold
        self.overlap_iou = overlap_iou
        self._on_update = on_stage_update

    # ------------------------------------------------------------------
    def _make_stages(self) -> List[StageResult]:
        return [StageResult(name=n) for n in STAGE_NAMES]

    def _start(self, stage: StageResult, message: str = "") -> None:
        stage.status = "running"
        stage.message = message
        if self._on_update:
            self._on_update(stage)

    def _done(self, stage: StageResult, message: str = "") -> None:
        stage.status = "done"
        stage.message = message
        stage.percent = STAGE_DONE_PCT[stage.name]
        if self._on_update:
            self._on_update(stage)

    def _fail(self, stage: StageResult, error_key: str) -> str:
        stage.status = "failed"
        msg = RETAKE_MESSAGES.get(error_key, "An error occurred. Please retake the photo.")
        stage.message = msg
        stage.percent = STAGE_DONE_PCT[stage.name]
        if self._on_update:
            self._on_update(stage)
        return msg

    # ------------------------------------------------------------------
    def run(self, image_bgr: np.ndarray) -> PipelineResult:
        """Run all six stages synchronously, returning a PipelineResult."""
        stages = self._make_stages()
        result = PipelineResult(stages=stages)
        by_name = {s.name: s for s in stages}

        # ── Stage 1: image_quality_check ──────────────────────────────
        s1 = by_name["image_quality_check"]
        self._start(s1, "Checking image sharpness…")
        is_blurry, variance = check_image_blur(image_bgr, threshold=self.blur_threshold)
        if is_blurry:
            retake = self._fail(s1, "image_quality_check__blur")
            result.failed_stage = s1.name
            result.retake_message = retake
            return result
        self._done(s1, f"Image quality OK (sharpness score: {variance:.0f})")

        # ── Stage 2: marker_detection ─────────────────────────────────
        s2 = by_name["marker_detection"]
        self._start(s2, "Looking for ArUco reference marker…")
        marker_info: Dict = {}

        if _HAS_ARUCO:
            marker_info = detect_aruco(image_bgr, marker_side_cm=self.marker_side_cm)
        else:
            marker_info = {
                "detected": False,
                "method": "none",
                "status": "not_found",
                "pixels_per_cm": None,
            }

        result.marker_info = marker_info
        if marker_info.get("detected"):
            method = marker_info.get("method", "aruco")
            if method == "coin_fallback":
                self._done(s2, "Coin fallback marker found (ArUco preferred for accuracy)")
                result.needs_attention = True
                result.attention_reason = "Marker not detected via ArUco; coin fallback used — size estimates may be less accurate."
            else:
                self._done(s2, f"ArUco marker detected (ID {marker_info.get('marker_id')}, "
                               f"{marker_info.get('pixels_per_cm', 0):.1f} px/cm)")
        else:
            # Marker not found — not a hard failure, but flag needs_attention
            self._done(s2, "Marker not found — size measurement will be skipped")
            result.needs_attention = True
            result.attention_reason = (
                "ArUco reference marker was not detected. "
                "Diameter measurements are unavailable; size-based grading may be inaccurate. "
                "Print the marker from /ml/make_marker.py and retake for accurate results."
            )

        # ── Stage 3: onion_detection ──────────────────────────────────
        s3 = by_name["onion_detection"]
        self._start(s3, "Running AI detection model…")
        raw_inference: Dict = {}

        if _HAS_INFER:
            raw_inference = ml_infer(image_bgr)
        else:
            # Shouldn't happen in production but guard gracefully
            raw_inference = {
                "detections": [],
                "marker_status": "not_found",
                "marker_pixels_per_cm": None,
                "total_detections": 0,
                "mock": True,
            }

        result.is_mock = raw_inference.get("mock", False)
        raw_detections: List[Dict] = raw_inference.get("detections", [])

        if len(raw_detections) == 0:
            retake = self._fail(s3, "onion_detection__none_found")
            result.failed_stage = s3.name
            result.retake_message = retake
            return result

        if len(raw_detections) < self.min_onion_count:
            # Soft flag, not a hard failure
            result.needs_attention = True
            reason_msg = (
                f"Only {len(raw_detections)} onion(s) detected "
                f"(minimum recommended: {self.min_onion_count}). "
                "Grade may not be statistically representative."
            )
            result.attention_reason = (result.attention_reason + " | " + reason_msg
                                       if result.attention_reason else reason_msg)

        # Overlapping check
        boxes = [d["bbox"] for d in raw_detections if "bbox" in d]
        is_overlapping, overlap_ratio = check_overlapping_boxes(boxes, iou_threshold=self.overlap_iou)
        if is_overlapping:
            retake = self._fail(s3, "onion_detection__too_overlapping")
            result.failed_stage = s3.name
            result.retake_message = retake
            return result

        self._done(s3, f"{len(raw_detections)} onion(s) detected")

        # ── Stage 4: size_measurement ─────────────────────────────────
        s4 = by_name["size_measurement"]
        self._start(s4, "Calibrating size from marker…")

        if _HAS_ARUCO:
            calibrated_detections = calibrate_detections_with_aruco(
                raw_detections, marker_info,
                fallback_pixels_per_cm=raw_inference.get("marker_pixels_per_cm"),
            )
        else:
            calibrated_detections = raw_detections

        has_diameters = any(d.get("diameter_cm") is not None for d in calibrated_detections)
        if not has_diameters and marker_info.get("detected"):
            retake = self._fail(s4, "size_measurement__no_calibration")
            result.failed_stage = s4.name
            result.retake_message = retake
            return result

        measured_count = sum(1 for d in calibrated_detections if d.get("diameter_cm") is not None)
        self._done(s4, f"Size measured for {measured_count}/{len(calibrated_detections)} onions")

        # ── Stage 5: defect_detection ─────────────────────────────────
        s5 = by_name["defect_detection"]
        self._start(s5, "Classifying defects…")

        confidences = [d.get("confidence", 1.0) for d in calibrated_detections]
        mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

        if mean_conf < self.min_confidence:
            result.needs_attention = True
            reason_msg = (
                f"Mean detection confidence is low ({mean_conf:.2f}). "
                "Results may be less accurate — consider retaking with better lighting."
            )
            result.attention_reason = (result.attention_reason + " | " + reason_msg
                                       if result.attention_reason else reason_msg)

        defect_counts: Dict[str, int] = {}
        for d in calibrated_detections:
            cls = d.get("class", "good")
            defect_counts[cls] = defect_counts.get(cls, 0) + 1

        defective_total = sum(v for k, v in defect_counts.items() if k != "good")
        self._done(s5, f"Defects: {defective_total}/{len(calibrated_detections)} "
                       f"(mean confidence: {mean_conf:.0%})")

        result.detections = calibrated_detections

        # ── Stage 6: grading ──────────────────────────────────────────
        s6 = by_name["grading"]
        self._start(s6, "Computing three-bucket grade…")

        onions_for_grade = [
            {"class": d.get("class", "good"), "diameter_cm": d.get("diameter_cm")}
            for d in calibrated_detections
        ]
        grade_data = compute_grade(onions_for_grade)
        result.grade_data = grade_data
        self._done(s6, (
            f"Grade: {grade_data.get('lot_grade_label', 'N/A')}  |  "
            f"A: {grade_data.get('grade_a_pct', 0):.1f}%  "
            f"URS: {grade_data.get('urs_pct', 0):.1f}%  "
            f"Def: {grade_data.get('defective_pct', 0):.1f}%"
        ))

        return result


# ────────────────────────────────────────────────────────────────────────────
# Convenience helper — build a "zero progress" stage list for serialisation
# ────────────────────────────────────────────────────────────────────────────
def initial_stage_list() -> List[Dict]:
    """Return the six stages in pending state (for immediate API response)."""
    return [
        {"name": n, "status": "pending", "message": "", "percent": 0}
        for n in STAGE_NAMES
    ]
