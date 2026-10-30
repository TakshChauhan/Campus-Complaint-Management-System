"""Sprint 3 demo seed: safety, idempotency and the feed visibility it demonstrates."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.complaint_hmc_audience import ComplaintHMCAudience
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.scripts import seed_sprint3_demo as demo
from app.scripts.seed_departments import seed_departments
from app.scripts.seed_dev_users import seed_development_users
from app.services.public_feed_service import valid_hmc_group
from sprint3_hmc_world import FORBIDDEN_FEED_KEYS, headers_for

HOSTEL_FEED = "/api/v1/feeds/hostel"
EXPECTED_STATUSES = {record["key"]: record["expected"] for record in demo.COMPLAINTS}
MODELS = (Hostel, HostelWing, HostelFloor, HMCGroup, HMCGroupFloor, User, StudentResidence,
          Complaint, ComplaintStatusHistory, ComplaintHMCAudience)


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("DEV_STUDENT_PASSWORD", "LocalDemoOnly123!")


@pytest.fixture
def seeded(db: Session, demo_env) -> dict:
    seed_departments(db)
    return demo.seed_sprint3_demo(db)


def _counts(db: Session) -> tuple:
    return tuple(db.query(model).count() for model in MODELS)


def _student(db: Session, key: str) -> User:
    return db.query(User).filter(User.email == demo._email(demo.STUDENTS[key][0])).one()


def _complaint_ids(db: Session) -> dict:
    by_title = {c.title: c.id for c in db.query(Complaint).all()}
    return {record["key"]: by_title[record["title"]] for record in demo.COMPLAINTS}


def _department_id(db: Session, name: str) -> int:
    return db.query(Department).filter(Department.name == name).one().id


def _assert_private(response) -> None:
    assert "@" not in response.text

    def walk(value):
        if isinstance(value, dict):
            assert not (set(value) & (FORBIDDEN_FEED_KEYS | {"created_by_id", "description"})), value
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(response.json())


def _feed(client, user: User, url: str = HOSTEL_FEED) -> set[int]:
    response = client.get(url, headers=headers_for(user))
    assert response.status_code == 200, response.text
    _assert_private(response)
    return {item["id"] for item in response.json()}


# --------------------------------------------------------------------------- safety

def test_seeding_rejected_outside_development(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="development/testing SQLite"):
        demo.seed_sprint3_demo(db=object())  # fails before touching any database


def test_seeding_rejected_for_non_sqlite_database_url(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://user:pw@db.example.supabase.co:5432/postgres")
    with pytest.raises(RuntimeError, match="development/testing SQLite"):
        demo.seed_sprint3_demo(db=object())


def test_seeding_rejected_for_non_sqlite_session():
    # create_engine does not connect, so nothing is contacted here.
    engine = create_engine("postgresql+psycopg://user:pw@127.0.0.1:1/unused")
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="development/testing SQLite"):
            demo.seed_sprint3_demo(session)
    engine.dispose()


def test_seed_requires_student_password(db, monkeypatch):
    monkeypatch.delenv("DEV_STUDENT_PASSWORD", raising=False)
    seed_departments(db)
    with pytest.raises(RuntimeError, match="DEV_STUDENT_PASSWORD"):
        demo.seed_sprint3_demo(db)
    assert db.query(Hostel).count() == 0


def test_seed_requires_departments(db, demo_env):
    with pytest.raises(RuntimeError, match="Run seed_departments first"):
        demo.seed_sprint3_demo(db)
    assert db.query(Hostel).count() == 0


# --------------------------------------------------------------------------- data

def test_seed_creates_expected_world_and_statuses(db, seeded):
    assert seeded["warnings"] == []
    assert seeded["complaints"] == EXPECTED_STATUSES
    assert _counts(db) == (2, 4, 12, 6, 12, 6, 4, 7, 7, 2)

    wings = {w.code: w.name for w in db.query(HostelWing).all()}
    assert wings == {"DEMO-H1-A": "Wing A", "DEMO-H1-B": "Wing B", "DEMO-H2-A": "Wing A", "DEMO-H2-B": "Wing B"}
    assert {(f.code, f.name) for f in db.query(HostelFloor).all()} == {("G", "Ground"), ("1", "Floor 1"), ("2", "Floor 2")}
    assert all(valid_hmc_group(db, group) for group in db.query(HMCGroup).all())

    hostel_staff = db.query(User).filter(User.email == demo._email(demo.HOSTEL_STAFF_LOCAL_PART)).one()
    for key, (_, _, _, verified) in demo.STUDENTS.items():
        residence = _student(db, key).residence
        assert residence.status == ("verified" if verified else "pending")
        assert residence.verified_by_id == (hostel_staff.id if verified else None)

    for complaint in db.query(Complaint).all():
        if complaint.department.name == "Hostel":
            assert complaint.floor_id is not None


def test_seed_is_idempotent(db, seeded):
    first = _counts(db)
    second = demo.seed_sprint3_demo(db)
    assert _counts(db) == first
    assert set(second["created"].values()) == {0}
    assert second["warnings"] == []
    assert second["complaints"] == EXPECTED_STATUSES


def test_seed_reuses_dev_admin(db, demo_env):
    from app.core.config import settings

    seed_departments(db)
    seed_development_users(db)
    admin = db.query(User).filter(User.email == settings.DEV_ADMIN_EMAIL.lower()).one()

    result = demo.seed_sprint3_demo(db)

    assert db.query(User).filter(User.role == "admin").all() == [admin]
    assert result["warnings"] == []


# --------------------------------------------------------------------------- feeds

def test_h1_student_sees_only_own_group_published_complaint(db, client, seeded):
    ids = _complaint_ids(db)
    for key in ("h1_student1", "h1_student2"):
        visible = _feed(client, _student(db, key))
        assert ids["C1"] in visible
        assert not visible & {ids["C2"], ids["C3"], ids["C4"]}
        assert visible == {ids["C1"]}


def test_h2_student_sees_only_h2_complaint(db, client, seeded):
    ids = _complaint_ids(db)
    assert _feed(client, _student(db, "h2_student")) == {ids["C4"]}


def test_hostel_staff_and_admin_see_all_authorized_hostel_complaints(db, client, seeded):
    from app.core.config import settings

    ids = _complaint_ids(db)
    staff = db.query(User).filter(User.email == demo._email(demo.HOSTEL_STAFF_LOCAL_PART)).one()
    admin = db.query(User).filter(User.email == settings.DEV_ADMIN_EMAIL.lower()).one()
    assert _feed(client, staff) == {ids["C1"], ids["C4"]}
    assert _feed(client, admin) == {ids["C1"], ids["C4"]}


def test_pending_residence_student_gets_residence_not_verified(db, client, seeded):
    response = client.get(HOSTEL_FEED, headers=headers_for(_student(db, "pending_student")))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "residence_not_verified"


def test_department_feeds_show_only_non_hostel_public_complaints(db, client, seeded):
    ids = _complaint_ids(db)
    hostel_ids = {ids[k] for k in ("C1", "C2", "C3", "C4")}
    viewer = _student(db, "h1_student1")

    it_feed = _feed(client, viewer, f"/api/v1/feeds/departments/{_department_id(db, 'IT Services')}")
    library_feed = _feed(client, viewer, f"/api/v1/feeds/departments/{_department_id(db, 'Library')}")
    assert it_feed == {ids["C5"], ids["C7"]}
    assert library_feed == {ids["C6"]}
    assert not (it_feed | library_feed) & hostel_ids

    response = client.get(f"/api/v1/feeds/departments/{_department_id(db, 'Hostel')}", headers=headers_for(viewer))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "hostel_feed_required"


def test_similar_title_triggers_duplicate_warning(db, client, seeded):
    ids = _complaint_ids(db)
    c7 = next(record for record in demo.COMPLAINTS if record["key"] == "C7")
    response = client.post(
        "/api/v1/complaints/duplicate-suggestions",
        headers=headers_for(_student(db, "h1_student2")),
        json={"title": c7["title"], "description": c7["description"]},
    )
    assert response.status_code == 200, response.text
    assert ids["C5"] in {match["id"] for match in response.json()["matches"]}
