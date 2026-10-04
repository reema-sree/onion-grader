"""Image quality check and retake guidance utilities."""

from typing import Dict, List, Tuple
import cv2
import numpy as np


class QualityCheckError(Exception):
    """Exception raised when an uploaded image fails capture quality checks."""

    def __init__(self, error_code: str, message: str, guidance: str):
        self.error_code = error_code
        self.message = message
        self.guidance = guidance
        super().__init__(message)


def check_image_blur(
    image: np.ndarray,
    threshold: float = 40.0
) -> Tuple[bool, float]:
    """Check if an image is too blurry using the Laplacian variance method.

    Returns:
        (is_blurry, variance_score)
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    is_blurry = variance < threshold
    return is_blurry, variance


def check_overlapping_boxes(
    boxes: List[List[float]],
    iou_threshold: float = 0.45,
    max_overlap_ratio: float = 0.30
) -> Tuple[bool, float]:
    """Check if too many onions in the detection list overlap heavily.

    Returns:
        (is_too_overlapping, overlap_ratio)
    """
    if len(boxes) < 2:
        return False, 0.0

    overlap_count = 0
    total_pairs = 0

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            total_pairs += 1
            b1 = boxes[i]
            b2 = boxes[j]

            # Compute Intersection over Union (IoU)
            x1 = max(b1[0], b2[0])
            y1 = max(b1[1], b2[1])
            x2 = min(b1[2], b2[2])
            y2 = min(b1[3], b2[3])

            inter_w = max(0.0, x2 - x1)
            inter_h = max(0.0, y2 - y1)
            inter_area = inter_w * inter_h

            area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
            area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
            union_area = area1 + area2 - inter_area

            iou = (inter_area / union_area) if union_area > 0 else 0.0
            if iou > iou_threshold:
                overlap_count += 1

    overlap_ratio = (overlap_count / total_pairs) if total_pairs > 0 else 0.0
    return (overlap_ratio > max_overlap_ratio), overlap_ratio


def validate_inference_quality(
    image: np.ndarray,
    inference_result: Dict,
    allow_mock_bypass: bool = False
) -> None:
    """Validate image and inference quality against retake rules.

    Raises QualityCheckError if any quality standard is violated.
    """
    is_mock = inference_result.get("mock", False)
    if is_mock and allow_mock_bypass:
        return

    # 1. Blur check
    is_blurry, variance = check_image_blur(image)
    if is_blurry:
        raise QualityCheckError(
            error_code="IMAGE_TOO_BLURRY",
            message="Image is too blurry to ensure accurate grading.",
            guidance="Please hold the camera steady, ensure good lighting, and retake the photo."
        )

    # 2. No onions found check
    detections = inference_result.get("detections", [])
    if len(detections) == 0:
        raise QualityCheckError(
            error_code="NO_ONIONS_FOUND",
            message="No onions were detected in the image.",
            guidance="Please place onions clearly in the centre of the camera frame against a plain background and retake."
        )

    # 3. Marker not found check
    marker_status = inference_result.get("marker_status", "not_found")
    if marker_status != "detected":
        raise QualityCheckError(
            error_code="MARKER_NOT_FOUND",
            message="Reference calibration marker (coin/card) was not detected.",
            guidance="Please place a standard Indian coin (e.g., ₹1, ₹2, ₹5) or calibration card beside the onions and retake."
        )

    # 4. Overlapping onions check
    boxes = [d["bbox"] for d in detections if "bbox" in d]
    is_overlapping, _ = check_overlapping_boxes(boxes)
    if is_overlapping:
        raise QualityCheckError(
            error_code="TOO_MANY_OVERLAPPING_ONIONS",
            message="Onions are overlapping too heavily for accurate segmentation.",
            guidance="Please spread the onions out on a flat surface so they do not overlap each other and retake."
        )
