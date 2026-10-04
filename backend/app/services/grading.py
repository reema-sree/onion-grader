"""Grading computation service.

Evaluates detected onions against configured grading rules to produce
three-bucket quality grade percentages (Grade A, URS, Defective), lot grade labels,
defect breakdowns, and summary statistics.
"""

from typing import Any, Dict, List, Optional, Tuple
from ..core.config import GradingRulesConfig, load_grading_rules


def determine_onion_bucket(
    cls_name: str,
    diameter_cm: Optional[float],
    min_size_cm: float = 6.0,
    class_bucket_mapping: Optional[Dict[str, str]] = None
) -> str:
    """Determine the quality bucket for an individual onion.
    
    Returns: 'grade_a', 'urs', or 'defective'
    """
    cls = str(cls_name).lower().strip()
    diameter = float(diameter_cm) if diameter_cm is not None else 0.0

    mapping = class_bucket_mapping or {
        "good": "grade_a_or_urs",
        "damaged": "defective",
        "rotten": "defective",
        "sprouted": "defective",
        "undersized": "urs",
    }

    target = mapping.get(cls)
    if target == "grade_a_or_urs" or cls == "good":
        return "grade_a" if diameter >= min_size_cm else "urs"
    elif target == "defective" or cls in {"damaged", "rotten", "sprouted"}:
        return "defective"
    elif target == "urs" or cls == "undersized":
        return "urs"
    elif target == "grade_a":
        return "grade_a"
    else:
        # Fallback for unexpected defect classes
        return "defective"


def evaluate_lot_grade(
    grade_a_pct: float,
    defective_pct: float,
    urs_pct: float,
    lot_grade_rules: Optional[List[Dict[str, Any]]] = None
) -> Tuple[str, str, float]:
    """Evaluate lot grade and formatted label based on configured rules.
    
    Evaluated in order: first match wins.
    Returns: (lot_grade, lot_grade_label, lot_grade_pct)
    """
    if not lot_grade_rules:
        lot_grade_rules = [
            {"grade": "Grade A", "condition": "grade_a_pct >= 70.0", "threshold": 70.0},
            {"grade": "Defective", "condition": "defective_pct >= 30.0", "threshold": 30.0},
            {"grade": "URS", "condition": "otherwise"}
        ]

    for rule in lot_grade_rules:
        grade_name = rule.get("grade", "")
        condition = rule.get("condition", "")
        threshold = float(rule.get("threshold", 0.0))

        if "grade_a_pct" in condition:
            if grade_a_pct >= threshold:
                return grade_name, f"{grade_name} ({grade_a_pct:.1f}%)", grade_a_pct
        elif "defective_pct" in condition:
            if defective_pct >= threshold:
                return grade_name, f"{grade_name} ({defective_pct:.1f}%)", defective_pct
        elif "urs_pct" in condition:
            if urs_pct >= threshold:
                return grade_name, f"{grade_name} ({urs_pct:.1f}%)", urs_pct
        elif "otherwise" in condition or condition == "default":
            # Show percentage of its own bucket
            pct = urs_pct if grade_name.upper() == "URS" else grade_a_pct
            return grade_name, f"{grade_name} ({pct:.1f}%)", pct

    # Default fallback
    return "URS", f"URS ({urs_pct:.1f}%)", urs_pct


def compute_grade(
    onions: List[Dict[str, Any]],
    rules: Optional[GradingRulesConfig] = None
) -> Dict[str, Any]:
    """Compute Grade A, URS, and Defective percentages and defect breakdown.

    Args:
        onions: List of onion detections, where each item is a dict with
                keys 'class' (or 'current_class') and 'diameter_cm'.
        rules: Optional GradingRulesConfig instance. If None, loads from config/grading_rules.yaml.

    Returns:
        Dict with keys:
            - grade_a_pct (float): Percentage of Grade A onions (0.0 to 100.0)
            - urs_pct (float): Percentage of URS onions (0.0 to 100.0)
            - defective_pct (float): Percentage of Defective onions (0.0 to 100.0)
            - total_onions (int): Total number of onions evaluated
            - grade_a_count (int): Raw count of Grade A onions
            - urs_count (int): Raw count of URS onions
            - defective_count (int): Raw count of Defective onions
            - lot_grade (str): E.g. "Grade A", "Defective", "URS"
            - lot_grade_label (str): E.g. "Grade A (72.5%)"
            - lot_grade_pct (float): Percentage of the lot's assigned bucket
            - defect_breakdown (dict): Breakdown per category with 'count' and 'pct'
            - raw_counts (dict): Raw count per category
            - rule_version (str): Version of the grading rules used
            - status (str): "ok" or "no_onions"
    """
    if rules is None:
        rules = load_grading_rules()

    min_size_cm = rules.min_size_cm
    rule_version = rules.version
    valid_defect_classes = rules.defect_classes
    class_bucket_mapping = rules.class_bucket_mapping
    lot_grade_rules = rules.lot_grade_rules

    # Initialize category counters
    raw_counts: Dict[str, int] = {cls_name: 0 for cls_name in valid_defect_classes}
    if "undersized" not in raw_counts:
        raw_counts["undersized"] = 0

    total_onions = len(onions)

    # Handle empty batch cleanly without zero division
    if total_onions == 0:
        defect_breakdown = {
            cls_name: {"count": 0, "pct": 0.0}
            for cls_name in raw_counts
        }
        return {
            "grade_a_pct": 0.0,
            "urs_pct": 0.0,
            "defective_pct": 0.0,
            "total_onions": 0,
            "grade_a_count": 0,
            "urs_count": 0,
            "defective_count": 0,
            "lot_grade": "N/A",
            "lot_grade_label": "No Onions",
            "lot_grade_pct": 0.0,
            "defect_breakdown": defect_breakdown,
            "raw_counts": raw_counts,
            "rule_version": rule_version,
            "status": "no_onions"
        }

    grade_a_count = 0
    urs_count = 0
    defective_count = 0

    for onion in onions:
        cls = str(onion.get("class") or onion.get("current_class") or "good").lower().strip()
        diameter = onion.get("diameter_cm")
        diameter_val = float(diameter) if diameter is not None else 0.0

        bucket = determine_onion_bucket(cls, diameter_val, min_size_cm, class_bucket_mapping)
        onion["bucket"] = bucket

        if bucket == "grade_a":
            grade_a_count += 1
            raw_counts["good"] = raw_counts.get("good", 0) + 1
        elif bucket == "urs":
            urs_count += 1
            if cls == "good":
                raw_counts["undersized"] = raw_counts.get("undersized", 0) + 1
            elif cls in raw_counts:
                raw_counts[cls] += 1
            else:
                raw_counts["undersized"] = raw_counts.get("undersized", 0) + 1
        else: # defective
            defective_count += 1
            if cls in raw_counts:
                raw_counts[cls] += 1
            else:
                raw_counts[cls] = raw_counts.get(cls, 0) + 1

    # Exact count-based percentages summing to 100.0%
    grade_a_pct = round((grade_a_count / total_onions) * 100.0, 2)
    defective_pct = round((defective_count / total_onions) * 100.0, 2)
    urs_pct = round(100.0 - grade_a_pct - defective_pct, 2)

    lot_grade, lot_grade_label, lot_grade_pct = evaluate_lot_grade(
        grade_a_pct, defective_pct, urs_pct, lot_grade_rules
    )

    defect_breakdown = {
        cls_name: {
            "count": count,
            "pct": round((count / total_onions) * 100.0, 2)
        }
        for cls_name, count in raw_counts.items()
    }

    return {
        "grade_a_pct": grade_a_pct,
        "urs_pct": urs_pct,
        "defective_pct": defective_pct,
        "total_onions": total_onions,
        "grade_a_count": grade_a_count,
        "urs_count": urs_count,
        "defective_count": defective_count,
        "lot_grade": lot_grade,
        "lot_grade_label": lot_grade_label,
        "lot_grade_pct": lot_grade_pct,
        "defect_breakdown": defect_breakdown,
        "raw_counts": raw_counts,
        "rule_version": rule_version,
        "status": "ok"
    }
