"""Unit and Integration tests for Staff/Admin Dashboard Analytics, Summaries, and Admin Governance."""

import yaml
import pytest
from backend.app.models.user import UserRole
from backend.app.core.config import DEFAULT_GRADING_RULES_PATH, load_grading_rules


def test_dashboard_summary_scoped_to_centre(client, staff_headers, seed_centre):
    """GET /dashboard/summary returns today's scanned, approved, and pending counts scoped to centre."""
    resp = client.get("/dashboard/summary", headers=staff_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "scanned_today" in data
    assert "approved_today" in data
    assert "pending_today" in data
    assert data["centre_id"] == seed_centre.id


def test_admin_summary_kpi_metrics(client, admin_headers):
    """GET /admin/summary returns total batches, centres, average Grade A %, and per-centre breakdown."""
    resp = client.get("/admin/summary?period=all", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_batches" in data
    assert "total_centres" in data
    assert "avg_grade_a_pct" in data
    assert "override_rate" in data
    assert "per_centre_grade_a" in data
    assert data["period"] == "all"


def test_dashboard_lots_filter_by_centre_and_status(client, staff_headers, seed_centre):
    """GET /dashboard/lots allows filtering by centre and status."""
    lot = client.post("/lots", json={"farmer_name": "Farmer Dash", "centre_id": seed_centre.id, "weight_kg": 100.0}, headers=staff_headers).json()

    resp = client.get(f"/dashboard/lots?centre_id={seed_centre.id}", headers=staff_headers)
    assert resp.status_code == 200
    lots = resp.json()
    assert any(l["id"] == lot["id"] for l in lots)

    resp_draft = client.get("/dashboard/lots?status=draft", headers=staff_headers)
    assert resp_draft.status_code == 200


def test_dashboard_analytics_aggregation(client, staff_headers, seed_centre):
    """GET /dashboard/analytics aggregates total inspections, averages, override rate, and centres."""
    resp = client.get("/dashboard/analytics", headers=staff_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "overview" in data
    assert "lots_per_centre" in data
    assert "timeline" in data
    assert "avg_grade_a_pct" in data["overview"]
    assert "override_dispute_rate_pct" in data["overview"]


def test_admin_list_users_and_toggle_active(client, admin_headers, seed_farmer):
    """GET /admin/users lists accounts; POST /admin/users/{id}/toggle-active changes is_active."""
    resp = client.get("/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 1

    initial_active = seed_farmer.is_active
    toggle_resp = client.post(f"/admin/users/{seed_farmer.id}/toggle-active", headers=admin_headers)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] != initial_active


def test_admin_centres_management(client, admin_headers):
    """GET /admin/centres lists centres; POST /admin/centres creates new centre."""
    centre_payload = {
        "code": "C04",
        "name": "Baramati Kisan Mandi",
        "district": "Pune",
        "state": "Maharashtra",
        "address": "Baramati, Pune District, Maharashtra",
        "is_active": True
    }
    create_resp = client.post("/admin/centres", json=centre_payload, headers=admin_headers)
    assert create_resp.status_code == 201
    assert create_resp.json()["name"] == "Baramati Kisan Mandi"
    assert create_resp.json()["code"] == "C04"

    list_resp = client.get("/admin/centres", headers=admin_headers)
    assert list_resp.status_code == 200
    names = [c["name"] for c in list_resp.json()]
    assert "Baramati Kisan Mandi" in names


def test_admin_update_grading_rules_versioning(client, admin_headers):
    """POST /admin/grading-rules updates rule thresholds and version tags."""
    # Backup existing YAML
    with open(DEFAULT_GRADING_RULES_PATH, "r", encoding="utf-8") as f:
        backup_content = f.read()

    try:
        update_payload = {
            "min_size_cm": 6.2,
            "grade_a_definition": "Updated Agmark Grade A threshold (6.2cm)",
            "urs_definition": "All below 6.2cm or defective",
            "defect_classes": ["good", "damaged", "rotten", "sprouted", "undersized"],
            "version": "v2.1"
        }
        resp = client.post("/admin/grading-rules", json=update_payload, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["min_size_cm"] == 6.2
        assert data["version"] == "v2.1"

        current_rules = load_grading_rules()
        assert current_rules.min_size_cm == 6.2
        assert current_rules.version == "v2.1"
    finally:
        # Restore original config
        with open(DEFAULT_GRADING_RULES_PATH, "w", encoding="utf-8") as f:
            f.write(backup_content)
