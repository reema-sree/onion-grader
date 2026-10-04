"""Annotate detected onions and reference marker onto image for PDF report inclusion."""

from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np

from ..models.onion_detection import OnionDetection

# Color palette for classes (BGR format for OpenCV)
CLASS_COLORS = {
    "good": (34, 139, 34),        # Forest Green
    "damaged": (0, 140, 255),     # Dark Orange
    "rotten": (0, 0, 220),        # Crimson Red
    "sprouted": (128, 0, 128),    # Purple
    "undersized": (0, 191, 255),  # Gold / Amber
}


def draw_annotated_lot_image(
    image_path: Path,
    detections: List[OnionDetection],
    output_path: Path,
    max_dimension: int = 1000
) -> Path:
    """Draw bounding boxes, labels, and override indicators on the lot image."""
    img = cv2.imread(str(image_path))
    if img is None:
        # Create a fallback blank canvas if image cannot be read
        img = np.ones((600, 800, 3), dtype=np.uint8) * 240
        cv2.putText(img, "Image not available", (200, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    h, w = img.shape[:2]

    # Resize if extremely large to maintain crisp rendering in PDF without bloating
    if max(h, w) > max_dimension:
        scale = max_dimension / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    for det in detections:
        bbox = det.bbox or [0, 0, 0, 0]
        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Clamp to image bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        cls_key = str(det.current_class).lower().strip()
        color = CLASS_COLORS.get(cls_key, (100, 100, 100))

        # 1. Draw Bounding Box
        thickness = 3 if det.is_overridden else 2
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

        # 2. Draw mask polygon if present
        if det.mask_polygon and len(det.mask_polygon) >= 3:
            pts = np.array(det.mask_polygon, np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], isClosed=True, color=color, thickness=1)

        # 3. Label text formatting
        diam_text = f" {det.diameter_cm:.1f}cm" if det.diameter_cm else ""
        label_text = f"{det.current_class.upper()}{diam_text}"
        if det.is_overridden:
            label_text = f"*OVR* {label_text}"

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        font_thickness = 1
        (tw, th), baseline = cv2.getTextSize(label_text, font, font_scale, font_thickness)

        # Draw label background tag
        tag_y1 = max(0, y1 - th - 6)
        tag_y2 = y1
        tag_x2 = min(w, x1 + tw + 6)
        cv2.rectangle(img, (x1, tag_y1), (tag_x2, tag_y2), color, -1)

        # Draw text in white
        cv2.putText(
            img,
            label_text,
            (x1 + 3, tag_y2 - 3),
            font,
            font_scale,
            (255, 255, 255),
            font_thickness,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    return output_path
