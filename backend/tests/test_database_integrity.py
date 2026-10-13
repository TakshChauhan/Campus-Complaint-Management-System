import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.models.complaint import Complaint
from app.models.department import Department
from app.models.user import User


@pytest.fixture
def integrity_db() -> Session:
    """Isolated database session with foreign key constraint enforcement explicitly enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, connection_record):
        if type(dbapi_connection).__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_complaint_foreign_key_ondelete_is_restrict():
    """Verify that Complaint foreign keys enforce RESTRICT ondelete."""
    # Check created_by_id foreign key
    created_by_fk = next(iter(Complaint.__table__.c.created_by_id.foreign_keys))
    assert created_by_fk.ondelete == "RESTRICT", (
        f"Expected created_by_id foreign key ondelete='RESTRICT', got '{created_by_fk.ondelete}'"
    )

    # Check department_id foreign key
    dept_fk = next(iter(Complaint.__table__.c.department_id.foreign_keys))
    assert dept_fk.ondelete == "RESTRICT", (
        f"Expected department_id foreign key ondelete='RESTRICT', got '{dept_fk.ondelete}'"
    )


def test_user_complaints_relationship_has_no_delete_cascade():
    """Verify that User.complaints relationship does not cascade deletions."""
    cascade_options = User.complaints.property.cascade
    assert "delete" not in cascade_options, (
        f"User.complaints relationship must not contain 'delete' cascade: {cascade_options}"
    )
    assert "delete-orphan" not in cascade_options, (
        f"User.complaints relationship must not contain 'delete-orphan' cascade: {cascade_options}"
    )


def test_user_deletion_does_not_delete_complaint_records(integrity_db: Session):
    """
    Verify that complaint records cannot be unintentionally wiped out when user deletion is attempted.
    The database must reject the deletion with an IntegrityError.
    """
    dept = Department(name="IT Services", is_active=True)
    user = User(name="Alice Student", email="alice@campus.edu", role="student", is_active=True)
    integrity_db.add_all([dept, user])
    integrity_db.commit()

    complaint = Complaint(
        title="Hostel Wi-Fi down",
        description="Wi-Fi connectivity dropped in hostel block C since morning",
        department_id=dept.id,
        created_by_id=user.id,
        status="submitted",
    )
    integrity_db.add(complaint)
    integrity_db.commit()

    complaint_id = complaint.id
    user_id = user.id

    # Attempting to delete the user who filed this complaint must fail with IntegrityError
    with pytest.raises(IntegrityError):
        integrity_db.delete(user)
        integrity_db.commit()

    integrity_db.rollback()

    # Verify that the complaint remains completely intact in the database
    persisted_complaint = integrity_db.query(Complaint).filter(Complaint.id == complaint_id).first()
    assert persisted_complaint is not None
    assert persisted_complaint.title == "Hostel Wi-Fi down"
    assert persisted_complaint.created_by_id == user_id
    assert persisted_complaint.status == "submitted"


def test_department_deletion_restricted_with_complaints(integrity_db: Session):
    """Verify that deleting a department with active complaints is restricted."""
    dept = Department(name="Hostel Facilities", is_active=True)
    user = User(name="Bob Student", email="bob@campus.edu", role="student", is_active=True)
    integrity_db.add_all([dept, user])
    integrity_db.commit()

    complaint = Complaint(
        title="Water issue in hostel",
        description="Low water pressure on second floor bathrooms",
        department_id=dept.id,
        created_by_id=user.id,
        status="submitted",
    )
    integrity_db.add(complaint)
    integrity_db.commit()

    complaint_id = complaint.id
    dept_id = dept.id

    # Attempting to delete the department must fail due to ondelete="RESTRICT"
    with pytest.raises(IntegrityError):
        integrity_db.delete(dept)
        integrity_db.commit()

    integrity_db.rollback()

    # Verify department and complaint still exist intact
    assert integrity_db.query(Department).filter(Department.id == dept_id).first() is not None
    assert integrity_db.query(Complaint).filter(Complaint.id == complaint_id).first() is not None


def test_soft_deactivation_preserves_complaints(integrity_db: Session):
    """
    Demonstrate correct lifecycle practice: Deactivating a student account (is_active=False)
    safely preserves all associated complaint audit records.
    """
    dept = Department(name="Library Facilities", is_active=True)
    user = User(name="Carol Student", email="carol@campus.edu", role="student", is_active=True)
    integrity_db.add_all([dept, user])
    integrity_db.commit()

    complaint = Complaint(
        title="Printer paper jam in library",
        description="Printer 2 keeps jamming during peak study hours",
        department_id=dept.id,
        created_by_id=user.id,
        status="submitted",
    )
    integrity_db.add(complaint)
    integrity_db.commit()

    # Deactivate the student account instead of hard deleting
    user.is_active = False
    integrity_db.commit()

    # Reload and verify complaint and creator
    reloaded_complaint = integrity_db.query(Complaint).filter(Complaint.id == complaint.id).first()
    assert reloaded_complaint is not None
    assert reloaded_complaint.creator.is_active is False
    assert reloaded_complaint.creator.id == user.id


def test_database_url_normalization_for_supabase():
    """Verify DATABASE_URL normalization supports Supabase and PostgreSQL connection schemes."""
    # Test postgres:// normalization
    raw_postgres = "postgres://postgres:pwd@db.projectref.supabase.co:5432/postgres?sslmode=require"
    normalized = Settings.normalize_database_url(raw_postgres)
    assert normalized.startswith("postgresql+psycopg://")
    assert "sslmode=require" in normalized

    # Test postgresql:// normalization
    raw_postgresql = "postgresql://postgres:pwd@db.projectref.supabase.co:5432/postgres?sslmode=require"
    normalized = Settings.normalize_database_url(raw_postgresql)
    assert normalized.startswith("postgresql+psycopg://")

    # Test postgresql+psycopg2:// normalization
    raw_psycopg2 = "postgresql+psycopg2://postgres:pwd@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    normalized = Settings.normalize_database_url(raw_psycopg2)
    assert normalized.startswith("postgresql+psycopg://")
