"""Unit tests for JWT authentication and role-based access control (RBAC)."""

from backend.app.models.user import UserRole


def test_register_requires_admin_token(client, farmer_headers, admin_headers, seed_centre):
    """Only admins can register users when users already exist in the database."""
    new_user_payload = {
        "name": "New Staff Member",
        "email": "new_staff@example.com",
        "password": "Password123!",
        "role": "staff",
        "centre_id": seed_centre.id,
        "preferred_language": "en"
    }

    # 1. Unauthenticated registration attempt
    resp_unauth = client.post("/auth/register", json=new_user_payload)
    assert resp_unauth.status_code == 401

    # 2. Farmer registration attempt (forbidden)
    resp_farmer = client.post("/auth/register", json=new_user_payload, headers=farmer_headers)
    assert resp_farmer.status_code == 403

    # 3. Admin registration attempt (allowed)
    resp_admin = client.post("/auth/register", json=new_user_payload, headers=admin_headers)
    assert resp_admin.status_code == 201
    data = resp_admin.json()
    assert data["email"] == "new_staff@example.com"
    assert data["role"] == "staff"
    assert "id" in data


def test_register_duplicate_email_fails(client, admin_headers, seed_admin):
    """Attempting to register an already-existing email returns 400 Bad Request."""
    payload = {
        "name": "Duplicate Admin",
        "email": seed_admin.email,
        "password": "AnotherPassword123!",
        "role": "farmer",
        "preferred_language": "en"
    }
    resp = client.post("/auth/register", json=payload, headers=admin_headers)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


def test_login_success_and_token_generation(client, seed_farmer):
    """Login with valid credentials returns a valid JWT bearer token."""
    login_payload = {
        "email": seed_farmer.email,
        "password": "FarmerPass123!"
    }
    resp = client.post("/auth/login", json=login_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == seed_farmer.email
    assert data["user"]["role"] == "farmer"


def test_login_invalid_password(client, seed_farmer):
    """Login with invalid password returns 401 Unauthorized."""
    login_payload = {
        "email": seed_farmer.email,
        "password": "WrongPassword!"
    }
    resp = client.post("/auth/login", json=login_payload)
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.json()["detail"]


def test_get_me_endpoint(client, farmer_headers, seed_farmer):
    """GET /auth/me returns currently authenticated user information."""
    resp = client.get("/auth/me", headers=farmer_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == seed_farmer.id
    assert data["email"] == seed_farmer.email
    assert data["role"] == "farmer"


def test_get_me_unauthenticated(client):
    """GET /auth/me without token returns 401."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401
