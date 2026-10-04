import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test configuration
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-1234567890"

from backend.app.main import create_app
from backend.app.db.base import Base
from backend.app.db import get_db
from backend.app.models.user import User, UserRole
from backend.app.models.centre import Centre
from backend.app.core.security import get_password_hash, create_access_token
from backend.app import models  # noqa: F401

# In-memory test engine
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def db_session():
    """Provides a transactional database session rolled back after each test."""
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_centre(db_session):
    centre = Centre(code="C01", name="Nashik APMC Centre", district="Nashik", state="Maharashtra", address="Nashik, Maharashtra")
    db_session.add(centre)
    db_session.commit()
    db_session.refresh(centre)
    return centre


@pytest.fixture
def seed_admin(db_session, seed_centre):
    admin = User(
        name="Admin User",
        email="admin@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        role=UserRole.ADMIN,
        centre_id=seed_centre.id,
        is_active=True
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def seed_farmer(db_session, seed_centre):
    farmer = User(
        name="Ramesh Farmer",
        email="farmer@example.com",
        hashed_password=get_password_hash("FarmerPass123!"),
        role=UserRole.FARMER,
        centre_id=seed_centre.id,
        is_active=True
    )
    db_session.add(farmer)
    db_session.commit()
    db_session.refresh(farmer)
    return farmer


@pytest.fixture
def seed_staff(db_session, seed_centre):
    staff = User(
        name="Suresh Staff",
        email="staff@example.com",
        hashed_password=get_password_hash("StaffPass123!"),
        role=UserRole.STAFF,
        centre_id=seed_centre.id,
        is_active=True
    )
    db_session.add(staff)
    db_session.commit()
    db_session.refresh(staff)
    return staff


@pytest.fixture
def admin_headers(seed_admin):
    token = create_access_token({"sub": str(seed_admin.id), "role": "admin", "email": seed_admin.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def farmer_headers(seed_farmer):
    token = create_access_token({"sub": str(seed_farmer.id), "role": "farmer", "email": seed_farmer.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_headers(seed_staff):
    token = create_access_token({"sub": str(seed_staff.id), "role": "staff", "email": seed_staff.email})
    return {"Authorization": f"Bearer {token}"}
