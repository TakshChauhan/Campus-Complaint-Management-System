"""Sprint 2 demo seed (22 student-sourced complaints) and the optional synthetic public fixture."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.user import User
from app.scripts.seed_departments import PROVISIONAL_DEPARTMENTS, seed_departments
from app.scripts import seed_sprint2_demo as base_seed
from app.scripts import seed_sprint2_synthetic_public as synthetic_seed

DEMO_STUDENT_EMAIL = "student@dau.ac.in"
EXPECTED_STAFF_EMAILS = {
    "Hostel": "demo.staff.hostel@dau.ac.in",
    "IT Services": "demo.staff.it.services@dau.ac.in",
    "Library": "demo.staff.library@dau.ac.in",
    "Mess & Cafeteria": "demo.staff.mess.cafeteria@dau.ac.in",
    "Sports & Gymnasium": "demo.staff.sports.gymnasium@dau.ac.in",
    "Campus Security": "demo.staff.campus.security@dau.ac.in",
    "Medical Facility": "demo.staff.medical.facility@dau.ac.in",
}
CONFIRMED_LOCATIONS = {
    "B304": ("Hostel", "B", "2"),
    "C top floor": ("Hostel", "C", "1"),
    "AB Top Floor Washroom": ("Hostel", "A", "2"),
    "M-102": ("Hostel", "M", "Ground"),
}
ALLOWED = {("submitted", "in_progress"), ("in_progress", "resolved"), ("resolved", "reopened"), ("reopened", "in_progress")}


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.delenv("DEV_STUDENT_EMAIL", raising=False)
    monkeypatch.setenv("DEV_STUDENT_PASSWORD", "LocalDemoOnly123!")


@pytest.fixture
def seeded(db: Session, demo_env) -> Session:
    seed_departments(db)
    base_seed.seed_sprint2_demo(db)
    return db


def _demo_records():
    return json.loads(base_seed.DATA_FILE.read_text(encoding="utf-8"))


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive UTC datetimes; PostgreSQL returns aware ones.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# --------------------------------------------------------------------------- base demo seed

def test_seed_creates_one_active_staff_account_per_department(seeded):
    staff = seeded.query(User).filter(User.role == "staff").all()
    by_department = {u.department.name: u for u in staff}

    assert len(staff) == len(PROVISIONAL_DEPARTMENTS) == 7
    assert {name: u.email for name, u in by_department.items()} == EXPECTED_STAFF_EMAILS
    for user in staff:
        assert user.is_active and user.email_verified
        assert user.email_verification_required is False
        assert user.password_hash and user.password_hash != "StaffSecret123!"


def test_seed_creates_exactly_the_22_expected_private_complaints(seeded):
    student = seeded.query(User).filter(User.email == DEMO_STUDENT_EMAIL).one()
    complaints = seeded.query(Complaint).order_by(Complaint.id).all()
    records = _demo_records()

    assert len(records) == 22
    assert len(complaints) == 22
    assert [c.title for c in complaints] == [r["title"].strip() for r in records]
    for complaint, record in zip(complaints, records):
        assert complaint.created_by_id == student.id
        assert complaint.department.name == record["department"]
        assert complaint.status == "submitted"
        assert complaint.is_public is False
        assert complaint.reopen_count == 0
        assert complaint.resolved_at is None
        assert (complaint.hostel, complaint.wing, complaint.floor) == (
            record.get("hostel"), record.get("wing"), record.get("floor")
        )


def test_demo_structured_locations_match_confirmed_hostel_mappings():
    # Campus-specific conventions confirmed by the team; every other location stays unstructured.
    for record in _demo_records():
        expected = CONFIRMED_LOCATIONS.get(record.get("location"), (None, None, None))
        actual = (record.get("hostel"), record.get("wing"), record.get("floor"))
        assert actual == expected, record["title"]


def test_seed_is_idempotent(seeded):
    counts = lambda: (  # noqa: E731
        seeded.query(User).count(),
        seeded.query(Complaint).count(),
        seeded.query(ComplaintStatusHistory).count(),
    )
    first = counts()
    base_seed.seed_sprint2_demo(seeded)
    assert counts() == first == (8, 22, 22)


def test_each_seeded_complaint_has_one_submitted_history_entry(seeded):
    student = seeded.query(User).filter(User.email == DEMO_STUDENT_EMAIL).one()
    for complaint in seeded.query(Complaint).all():
        assert len(complaint.status_history) == 1
        entry = complaint.status_history[0]
        assert entry.complaint is complaint
        assert (entry.from_status, entry.to_status) == (None, "submitted")
        assert entry.actor_id == student.id
        assert entry.created_at is not None


def test_complaint_privacy_defaults_to_false(db, seeded_departments, student_user):
    complaint = Complaint(
        title="Default privacy",
        description="Created without an explicit is_public value.",
        department_id=seeded_departments["it"].id,
        created_by_id=student_user.id,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    assert complaint.is_public is False
    assert complaint.reopen_count == 0
    assert complaint.updated_at is not None


def test_seed_keeps_existing_department_staff(db, demo_env):
    seed_departments(db)
    it = db.query(Department).filter(Department.name == "IT Services").one()
    db.add(User(name="Existing IT", email="existing.it@dau.ac.in", password_hash="x", role="staff",
                department_id=it.id, is_active=True))
    db.commit()

    base_seed.seed_sprint2_demo(db)

    it_staff = db.query(User).filter(User.role == "staff", User.department_id == it.id).all()
    assert [u.email for u in it_staff] == ["existing.it@dau.ac.in"]


def test_seed_requires_student_password_when_student_is_missing(db, monkeypatch):
    monkeypatch.delenv("DEV_STUDENT_EMAIL", raising=False)
    monkeypatch.delenv("DEV_STUDENT_PASSWORD", raising=False)
    seed_departments(db)
    with pytest.raises(RuntimeError, match="DEV_STUDENT_PASSWORD"):
        base_seed.seed_sprint2_demo(db)


@pytest.mark.parametrize("seeder", [base_seed.seed_sprint2_demo, synthetic_seed.seed_sprint2_synthetic_public])
def test_seeding_rejected_outside_development(monkeypatch, seeder):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="development/testing SQLite"):
        seeder(db=object())  # fails before touching any database


@pytest.mark.parametrize("seeder", [base_seed.seed_sprint2_demo, synthetic_seed.seed_sprint2_synthetic_public])
def test_seeding_rejected_for_non_sqlite_database_url(monkeypatch, seeder):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://user:pw@db.example.supabase.co:5432/postgres")
    with pytest.raises(RuntimeError, match="development/testing SQLite"):
        seeder(db=object())


@pytest.mark.parametrize("seeder", [base_seed.seed_sprint2_demo, synthetic_seed.seed_sprint2_synthetic_public])
def test_seeding_rejected_for_non_sqlite_session(seeder):
    # create_engine does not connect, so nothing is contacted here.
    engine = create_engine("postgresql+psycopg://user:pw@127.0.0.1:1/unused")
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="development/testing SQLite"):
            seeder(session)
    engine.dispose()


# --------------------------------------------------------------------------- optional synthetic fixture

def test_base_seed_creates_no_public_or_progressed_complaints(seeded):
    assert seeded.query(Complaint).filter(Complaint.is_public.is_(True)).count() == 0
    assert seeded.query(Complaint).filter(Complaint.status != "submitted").count() == 0


def test_synthetic_fixture_requires_department_staff(db):
    seed_departments(db)
    with pytest.raises(RuntimeError, match="No active staff"):
        synthetic_seed.seed_sprint2_synthetic_public(db)


def test_synthetic_fixture_histories_are_valid_and_consistent(seeded):
    created = synthetic_seed.seed_sprint2_synthetic_public(seeded)
    fixture = synthetic_seed.load_fixture()
    author = seeded.query(User).filter(User.email == fixture["author"]["email"]).one()
    complaints = seeded.query(Complaint).filter(Complaint.created_by_id == author.id).all()
    now = datetime.now(timezone.utc)

    assert created == len(fixture["complaints"]) == len(complaints)
    assert author.role == "student" and author.password_hash is None
    assert {c.status for c in complaints} == {"submitted", "in_progress", "resolved"}
    assert any(c.reopen_count for c in complaints)

    for c in complaints:
        assert c.is_public is True
        history = c.status_history
        assert history[0].from_status is None and history[0].to_status == "submitted"
        assert history[0].actor_id == author.id
        assert history[0].remark == synthetic_seed.SYNTHETIC_REMARK
        for previous, entry in zip(history, history[1:]):
            assert entry.from_status == previous.to_status
            assert (entry.from_status, entry.to_status) in ALLOWED
            assert _as_utc(entry.created_at) > _as_utc(previous.created_at)
            actor = seeded.get(User, entry.actor_id)
            if entry.to_status == "reopened":
                assert actor.id == author.id
            else:
                assert actor.role == "staff" and actor.department_id == c.department_id
        assert history[-1].to_status == c.status
        assert _as_utc(c.created_at) == _as_utc(history[0].created_at)
        assert _as_utc(c.updated_at) == _as_utc(history[-1].created_at)
        assert _as_utc(history[-1].created_at) < now
        assert c.reopen_count == sum(h.to_status == "reopened" for h in history)
        if c.status == "resolved":
            last_resolution = [h for h in history if h.to_status == "resolved"][-1]
            assert _as_utc(c.resolved_at) == _as_utc(last_resolution.created_at)
            assert _as_utc(c.resolved_at) > now - timedelta(days=30)
        else:
            assert c.resolved_at is None


def test_synthetic_fixture_is_idempotent_and_leaves_real_complaints_untouched(seeded):
    synthetic_seed.seed_sprint2_synthetic_public(seeded)
    total = seeded.query(Complaint).count()
    history_total = seeded.query(ComplaintStatusHistory).count()

    assert synthetic_seed.seed_sprint2_synthetic_public(seeded) == 0
    assert seeded.query(Complaint).count() == total
    assert seeded.query(ComplaintStatusHistory).count() == history_total

    student = seeded.query(User).filter(User.email == DEMO_STUDENT_EMAIL).one()
    real = seeded.query(Complaint).filter(Complaint.created_by_id == student.id).all()
    assert len(real) == 22
    assert all(not c.is_public and c.status == "submitted" and len(c.status_history) == 1 for c in real)
