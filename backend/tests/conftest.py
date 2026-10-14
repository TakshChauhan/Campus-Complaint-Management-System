import os
import sys

# Ensure backend root is on Python sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Force test settings before loading application
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-and-integration-tests"

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.department import Department
from app.models.user import User

# In-memory SQLite engine for tests with thread sharing enabled
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all database tables once for the test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a clean transactional session for each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden database session."""
    from app.core.rate_limit import auth_rate_limiter
    auth_rate_limiter.reset()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    auth_rate_limiter.reset()


@pytest.fixture
def seeded_departments(db: Session) -> dict:
    """Seed test departments: both active and inactive."""
    it_dept = Department(
        name="IT Services",
        description="Campus IT support and Wi-Fi",
        is_active=True,
    )
    hostel_dept = Department(
        name="Hostel",
        description="Hostel residential facilities",
        is_active=True,
    )
    library_dept = Department(
        name="Library",
        description="Library books and quiet study",
        is_active=True,
    )
    inactive_dept = Department(
        name="Printing Press (Archived)",
        description="Legacy printing facility",
        is_active=False,
    )

    db.add_all([it_dept, hostel_dept, library_dept, inactive_dept])
    db.commit()
    db.refresh(it_dept)
    db.refresh(hostel_dept)
    db.refresh(library_dept)
    db.refresh(inactive_dept)

    return {
        "it": it_dept,
        "hostel": hostel_dept,
        "library": library_dept,
        "inactive": inactive_dept,
    }


@pytest.fixture
def student_user(db: Session) -> User:
    """Create a verified student user."""
    user = User(
        name="Student Alice",
        email="alice@student.campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def student_headers(student_user: User) -> dict:
    """Bearer token headers for Student Alice."""
    token = create_access_token(
        subject=str(student_user.id),
        claims={"role": student_user.role, "email": student_user.email},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_b_user(db: Session) -> User:
    """Create a second distinct student user (Student Bob)."""
    user = User(
        name="Student Bob",
        email="bob@student.campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def student_b_headers(student_b_user: User) -> dict:
    """Bearer token headers for Student Bob."""
    token = create_access_token(
        subject=str(student_b_user.id),
        claims={"role": student_b_user.role, "email": student_b_user.email},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_user(db: Session) -> User:
    """Create a staff user."""
    user = User(
        name="Staff John",
        email="john.staff@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="staff",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def staff_headers(staff_user: User) -> dict:
    """Bearer token headers for Staff John."""
    token = create_access_token(
        subject=str(staff_user.id),
        claims={"role": staff_user.role, "email": staff_user.email},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session) -> User:
    """Create an administrator user."""
    user = User(
        name="Admin Chief",
        email="chief.admin@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    """Bearer token headers for Admin Chief."""
    token = create_access_token(
        subject=str(admin_user.id),
        claims={"role": admin_user.role, "email": admin_user.email},
    )
    return {"Authorization": f"Bearer {token}"}
