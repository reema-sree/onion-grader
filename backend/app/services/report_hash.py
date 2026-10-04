"""Canonical JSON hashing service for tamper-evident Kisan Setu / AgriGrade reports."""

import hashlib
import json
from typing import Any, Dict, List
from ..models.grade_result import GradeResult
from ..models.lot import Lot
from ..models.onion_detection import OnionDetection


def build_canonical_report_payload(
    lot: Lot,
    grade_result: GradeResult,
    detections: List[OnionDetection],
    version: int,
) -> Dict[str, Any]:
    """Construct a strictly structured dictionary for deterministic hashing.

    All floats are formatted to fixed decimal places, keys are sorted, and all
    child detection elements are ordered by ID.
    """
    # Canonical defect breakdown with fixed formatting
    raw_breakdown = grade_result.defect_breakdown or {}
    canonical_breakdown = {}
    for k in sorted(raw_breakdown.keys()):
        item = raw_breakdown[k]
        canonical_breakdown[k] = {
            "count": int(item.get("count", 0)),
            "pct": f"{float(item.get('pct', 0.0)):.2f}",
        }

    # Canonical raw counts
    raw_counts = grade_result.raw_counts or {}
    canonical_raw_counts = {
        k: int(raw_counts[k]) for k in sorted(raw_counts.keys())
    }

    # Canonical detections list
    sorted_dets = sorted(detections, key=lambda d: d.id)
    canonical_detections = []
    for d in sorted_dets:
        diam_str = f"{float(d.diameter_cm):.2f}" if d.diameter_cm is not None else "null"
        canonical_detections.append({
            "detection_id": d.id,
            "original_class": str(d.original_class).lower().strip(),
            "current_class": str(d.current_class).lower().strip(),
            "bucket": str(getattr(d, "bucket", "grade_a")).lower().strip(),
            "diameter_cm": diam_str,
            "is_overridden": bool(d.is_overridden),
        })

    centre_name = lot.centre.name if lot.centre else f"Centre-{lot.centre_id}"
    farmer_display = lot.farmer.name if lot.farmer else (lot.farmer_name or "Farmer")

    return {
        "batch_code": str(getattr(lot, "batch_code", None) or lot.lot_number or f"LOT-{lot.id}"),
        "centre_id": int(lot.centre_id),
        "centre_name": str(centre_name),
        "defective_pct": f"{float(getattr(grade_result, 'defective_pct', 0.0) or 0.0):.2f}",
        "defect_breakdown": canonical_breakdown,
        "detections": canonical_detections,
        "farmer_name": str(farmer_display).strip(),
        "grade_a_pct": f"{float(grade_result.grade_a_pct):.2f}",
        "lot_grade": str(getattr(grade_result, "lot_grade", "") or ""),
        "lot_id": int(lot.id),
        "raw_counts": canonical_raw_counts,
        "rule_version": str(grade_result.rule_version),
        "total_count": int(grade_result.total_count),
        "urs_pct": f"{float(grade_result.urs_pct):.2f}",
        "version": int(version),
        "weight_kg": f"{float(lot.weight_kg or 0.0):.2f}",
    }


def compute_canonical_hash(payload: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash over canonical JSON representation."""
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
