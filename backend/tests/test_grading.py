"""Unit tests for three-bucket compute_grade function and grading rules config."""

import pytest
from backend.app.services.grading import compute_grade
from backend.app.core.config import load_grading_rules, GradingRulesConfig


def test_empty_batch():
    """Empty batch must return zeros, clear status, and never divide by zero."""
    result = compute_grade([])
    assert result["total_onions"] == 0
    assert result["grade_a_pct"] == 0.0
    assert result["urs_pct"] == 0.0
    assert result["defective_pct"] == 0.0
    assert result["grade_a_count"] == 0
    assert result["urs_count"] == 0
    assert result["defective_count"] == 0
    assert result["status"] == "no_onions"
    assert result["lot_grade"] == "N/A"
    assert "defect_breakdown" in result
    assert result["defect_breakdown"]["good"]["count"] == 0
    assert result["defect_breakdown"]["good"]["pct"] == 0.0


def test_all_good_meeting_size():
    """All onions good and >= 6.0cm must result in 100% Grade A and 0% URS/Defective."""
    onions = [
        {"class": "good", "diameter_cm": 6.5},
        {"class": "good", "diameter_cm": 7.0},
        {"class": "good", "diameter_cm": 6.0},
    ]
    result = compute_grade(onions)
    assert result["total_onions"] == 3
    assert result["grade_a_pct"] == 100.0
    assert result["urs_pct"] == 0.0
    assert result["defective_pct"] == 0.0
    assert result["grade_a_count"] == 3
    assert result["urs_count"] == 0
    assert result["defective_count"] == 0
    assert result["status"] == "ok"
    assert result["lot_grade"] == "Grade A"
    assert result["defect_breakdown"]["good"]["count"] == 3
    assert result["defect_breakdown"]["good"]["pct"] == 100.0


def test_all_rotten():
    """All rotten onions must result in 0% Grade A, 0% URS, and 100% Defective."""
    onions = [
        {"class": "rotten", "diameter_cm": 6.5},
        {"class": "rotten", "diameter_cm": 8.0},
    ]
    result = compute_grade(onions)
    assert result["total_onions"] == 2
    assert result["grade_a_pct"] == 0.0
    assert result["urs_pct"] == 0.0
    assert result["defective_pct"] == 100.0
    assert result["grade_a_count"] == 0
    assert result["urs_count"] == 0
    assert result["defective_count"] == 2
    assert result["lot_grade"] == "Defective"
    assert result["defect_breakdown"]["rotten"]["count"] == 2
    assert result["defect_breakdown"]["rotten"]["pct"] == 100.0


def test_size_boundary():
    """Threshold boundary testing at 6.0 cm."""
    onions = [
        {"class": "good", "diameter_cm": 6.0},    # Exactly at boundary -> Grade A
        {"class": "good", "diameter_cm": 5.99},   # Just below boundary -> URS (undersized)
        {"class": "good", "diameter_cm": 6.01},   # Just above boundary -> Grade A
    ]
    result = compute_grade(onions)
    assert result["total_onions"] == 3
    assert result["grade_a_count"] == 2
    assert result["urs_count"] == 1
    assert result["defective_count"] == 0
    assert result["grade_a_pct"] == 66.67
    assert result["urs_pct"] == 33.33
    assert result["defective_pct"] == 0.0
    assert result["defect_breakdown"]["good"]["count"] == 2
    assert result["defect_breakdown"]["undersized"]["count"] == 1


def test_defect_precedence_over_undersized():
    """If an onion is both a defect class and undersized, it is bucketed as Defective."""
    onions = [
        {"class": "damaged", "diameter_cm": 4.5}, # Defective
        {"class": "rotten", "diameter_cm": 7.5},  # Defective
        {"class": "good", "diameter_cm": 4.0},    # URS (undersized)
        {"class": "good", "diameter_cm": 6.5},    # Grade A
    ]
    result = compute_grade(onions)
    assert result["total_onions"] == 4
    assert result["grade_a_count"] == 1
    assert result["urs_count"] == 1
    assert result["defective_count"] == 2
    assert result["grade_a_pct"] == 25.0
    assert result["urs_pct"] == 25.0
    assert result["defective_pct"] == 50.0

    assert result["defect_breakdown"]["damaged"]["count"] == 1
    assert result["defect_breakdown"]["rotten"]["count"] == 1
    assert result["defect_breakdown"]["undersized"]["count"] == 1
    assert result["defect_breakdown"]["good"]["count"] == 1


def test_percentages_always_sum_to_100():
    """Grade A % + URS % + Defective % must always equal 100% for non-empty batches."""
    test_cases = [
        [{"class": "good", "diameter_cm": 6.5}],
        [{"class": "good", "diameter_cm": 6.5}, {"class": "sprouted", "diameter_cm": 6.5}],
        [{"class": "good", "diameter_cm": 6.5}, {"class": "good", "diameter_cm": 5.0}, {"class": "rotten", "diameter_cm": 7.0}],
        [{"class": "damaged", "diameter_cm": 4.0}] * 7 + [{"class": "good", "diameter_cm": 6.5}] * 3,
    ]
    for batch in test_cases:
        res = compute_grade(batch)
        total_pct = round(res["grade_a_pct"] + res["urs_pct"] + res["defective_pct"], 2)
        assert total_pct == 100.0


def test_grading_rules_pydantic_validation():
    """Pydantic config model validates rules and defect classes."""
    rules = load_grading_rules()
    assert rules.min_size_cm == 6.0
    assert "good" in rules.defect_classes
    assert "rotten" in rules.defect_classes
    assert rules.version == "v2.0"

    # Invalid config missing required defect classes should fail
    with pytest.raises(ValueError):
        GradingRulesConfig(
            min_size_cm=5.0,
            defect_classes=["good"],  # missing rotten, damaged, etc.
            version="v2.0"
        )
