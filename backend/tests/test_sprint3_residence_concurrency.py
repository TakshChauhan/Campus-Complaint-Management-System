"""Residence concurrency and simultaneous decision conflict tests (S3-15 carryover)."""

import os
import threading
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.main import app
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.residence import ResidenceDecision
from app.services.residence_service import decide_residence
from sprint3_hmc_world import build_world, headers_for, make_user, set_residence

MY_RESIDENCE = "/api/v1/users/me/residence"
QUEUE = "/api/v1/staff/residences"


def decide_url(residence_id: int) -> str:
    return f"{QUEUE}/{residence_id}/decision"


@pytest.fixture
def world(db: Session, seeded_departments: dict, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


def test_concurrent_simultaneous_decisions_with_separate_sessions(tmp_path):
    """Two simultaneous review decisions executed concurrently via separate database
    sessions: exactly one must commit successfully and the second must receive HTTP 409.
    Uses an isolated file database to allow independent concurrent connections.
    """
    db_file = tmp_path / "residence_concurrency.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    setup_db = SessionFactory()
    try:
        # Create department
        hostel_dept = Department(name="Hostel", description="Hostel facilities", is_active=True)
        setup_db.add(hostel_dept)
        setup_db.flush()

        # Create hostel, wing, floor
        hostel = Hostel(code="H_CONC", name="Concurrency Hostel", is_active=True)
        setup_db.add(hostel)
        setup_db.flush()

        wing = HostelWing(hostel_id=hostel.id, code="W_CONC", name="Wing Conc", is_active=True)
        setup_db.add(wing)
        setup_db.flush()

        floor = HostelFloor(wing_id=wing.id, code="F_CONC", name="Floor Conc", is_active=True)
        setup_db.add(floor)
        setup_db.flush()

        now = datetime.now(timezone.utc)
        student = User(name="Student Conc", email="student_conc@dau.ac.in", role="student", is_active=True)
        staff = User(name="Staff Conc", email="staff_conc@campus.edu", role="staff", is_active=True, department_id=hostel_dept.id)
        admin = User(name="Admin Conc", email="admin_conc@campus.edu", role="admin", is_active=True)
        setup_db.add_all([student, staff, admin])
        setup_db.flush()

        residence = StudentResidence(
            student_id=student.id,
            floor_id=floor.id,
            status="pending",
            submitted_at=now,
            updated_at=now,
        )
        setup_db.add(residence)
        setup_db.commit()
        residence_id = residence.id
        staff_id = staff.id
        admin_id = admin.id
    finally:
        setup_db.close()

    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def run_review(user_id: int, decision: str, remark: str | None = None):
        session = SessionFactory()
        try:
            user = session.query(User).filter_by(id=user_id).one()
            barrier.wait(timeout=5)
            payload = ResidenceDecision(decision=decision, remark=remark)
            res = decide_residence(session, reviewer=user, residence_id=residence_id, payload=payload)
            with lock:
                results.append(("ok", res.status))
        except HTTPException as exc:
            with lock:
                results.append(("error", exc.status_code))
        except Exception as exc:
            with lock:
                results.append(("unexpected", f"{type(exc).__name__}: {exc}"))
        finally:
            session.close()

    t1 = threading.Thread(target=run_review, args=(staff_id, "approve", None))
    t2 = threading.Thread(target=run_review, args=(admin_id, "reject", "Late reject"))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    statuses = [r[0] for r in results]
    assert len(statuses) == 2, f"Expected 2 results, got {results}"
    assert statuses.count("ok") == 1, f"Expected exactly one success, got: {results}"
    assert statuses.count("error") == 1, f"Expected exactly one conflict error, got: {results}"

    error_code = [r[1] for r in results if r[0] == "error"][0]
    assert error_code == 409

    # Verify final database record is consistent
    verify_db = SessionFactory()
    try:
        final_record = verify_db.query(StudentResidence).filter_by(id=residence_id).one()
        assert final_record.status in ("verified", "rejected")
        assert final_record.decided_at is not None
        assert final_record.verified_by_id in (staff_id, admin_id)
    finally:
        verify_db.close()
        engine.dispose()


@pytest.mark.skipif(
    not (os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL") or os.getenv("TEST_POSTGRESQL_URL")),
    reason="Requires PostgreSQL test database (CCMS_DISPOSABLE_TEST_POSTGRES_URL or TEST_POSTGRESQL_URL)",
)
def test_postgresql_concurrent_simultaneous_decisions():
    """PostgreSQL-specific simultaneous decisions with separate connections and sessions:
    ensures row-level locking / conditional update returns one 200 and one 409.
    """
    pg_url = os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL") or os.getenv("TEST_POSTGRESQL_URL")
    engine = create_engine(pg_url)
    Base.metadata.create_all(bind=engine)
    PgSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    setup_db = PgSession()
    try:
        dept = setup_db.query(Department).filter_by(name="Hostel").first()
        if not dept:
            dept = Department(name="Hostel", description="Hostel facilities", is_active=True)
            setup_db.add(dept)
            setup_db.flush()

        hostel = setup_db.query(Hostel).filter_by(code="PG_H").first()
        if not hostel:
            hostel = Hostel(code="PG_H", name="PG Hostel", is_active=True)
            setup_db.add(hostel)
            setup_db.flush()
            wing = HostelWing(hostel_id=hostel.id, code="PG_H_W", name="PG Wing", is_active=True)
            setup_db.add(wing)
            setup_db.flush()
            floor = HostelFloor(wing_id=wing.id, code="PG_H_F1", name="PG Floor 1", is_active=True)
            setup_db.add(floor)
            setup_db.flush()
        else:
            floor = setup_db.query(HostelFloor).filter_by(code="PG_H_F1").first()

        now = datetime.now(timezone.utc)
        student = User(name="PG Student", email=f"pg_student_{now.timestamp()}@dau.ac.in", role="student", is_active=True)
        staff = User(name="PG Staff", email=f"pg_staff_{now.timestamp()}@campus.edu", role="staff", is_active=True, department_id=dept.id)
        admin = User(name="PG Admin", email=f"pg_admin_{now.timestamp()}@campus.edu", role="admin", is_active=True)
        setup_db.add_all([student, staff, admin])
        setup_db.flush()

        residence = StudentResidence(
            student_id=student.id,
            floor_id=floor.id,
            status="pending",
            submitted_at=now,
            updated_at=now,
        )
        setup_db.add(residence)
        setup_db.commit()
        residence_id = residence.id
        staff_id = staff.id
        admin_id = admin.id
    finally:
        setup_db.close()

    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def run_pg_decision(user_id: int, decision: str, remark: str | None = None):
        session = PgSession()
        try:
            user = session.query(User).filter_by(id=user_id).one()
            barrier.wait(timeout=5)
            payload = ResidenceDecision(decision=decision, remark=remark)
            res = decide_residence(session, reviewer=user, residence_id=residence_id, payload=payload)
            with lock:
                results.append(("ok", res.status))
        except HTTPException as exc:
            with lock:
                results.append(("error", exc.status_code))
        except Exception as exc:
            with lock:
                results.append(("unexpected", str(exc)))
        finally:
            session.close()

    t1 = threading.Thread(target=run_pg_decision, args=(staff_id, "approve", None))
    t2 = threading.Thread(target=run_pg_decision, args=(admin_id, "reject", "PG Rejection"))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    statuses = [r[0] for r in results]
    assert statuses.count("ok") == 1
    assert statuses.count("error") == 1
    assert [r[1] for r in results if r[0] == "error"][0] == 409

    engine.dispose()


def test_second_decision_returns_409_and_changes_nothing(
    client: TestClient,
    db: Session,
    world: dict,
):
    """A second decision on the same residence returns 409 and changes nothing
    (status, remark, verifier, time).
    """
    student = make_user(db, "student_concurrent_1", "student")
    staff_headers = headers_for(world["hostel_staff"])

    # Student declares residence
    res = client.patch(
        MY_RESIDENCE,
        headers=headers_for(student),
        json={"floor_id": world["floors"]["A1"].id},
    )
    assert res.status_code == 200

    residence = db.query(StudentResidence).filter_by(student_id=student.id).one()
    residence_id = residence.id

    # First decision: approve
    first_resp = client.post(
        decide_url(residence_id),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert first_data["status"] == "verified"
    decided_at = first_data["decided_at"]
    assert decided_at is not None

    db.expire_all()
    record_after_first = db.query(StudentResidence).filter_by(id=residence_id).one()
    initial_status = record_after_first.status
    initial_remark = record_after_first.remark
    initial_verifier = record_after_first.verified_by_id
    initial_time = record_after_first.verified_at

    # Second decision: attempt to approve again -> 409
    dup_approve = client.post(
        decide_url(residence_id),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert dup_approve.status_code == 409

    # Verify nothing was changed in the DB
    db.expire_all()
    record_after_dup = db.query(StudentResidence).filter_by(id=residence_id).one()
    assert record_after_dup.status == initial_status
    assert record_after_dup.remark == initial_remark
    assert record_after_dup.verified_by_id == initial_verifier
    assert record_after_dup.verified_at == initial_time


def test_approve_then_reject_and_reject_then_approve_both_give_409(
    client: TestClient,
    db: Session,
    world: dict,
):
    """approve-then-reject and reject-then-approve both yield 409 Conflict."""
    staff_headers = headers_for(world["hostel_staff"])

    # Sub-case A: approve then reject
    student_a = make_user(db, "student_app_rej", "student")
    client.patch(
        MY_RESIDENCE,
        headers=headers_for(student_a),
        json={"floor_id": world["floors"]["A1"].id},
    )
    res_a_id = db.query(StudentResidence).filter_by(student_id=student_a.id).one().id

    approve_resp = client.post(
        decide_url(res_a_id),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert approve_resp.status_code == 200

    reject_after_approve = client.post(
        decide_url(res_a_id),
        headers=staff_headers,
        json={"decision": "reject", "remark": "Attempting late rejection"},
    )
    assert reject_after_approve.status_code == 409

    # Sub-case B: reject then approve
    student_b = make_user(db, "student_rej_app", "student")
    client.patch(
        MY_RESIDENCE,
        headers=headers_for(student_b),
        json={"floor_id": world["floors"]["B1"].id},
    )
    res_b_id = db.query(StudentResidence).filter_by(student_id=student_b.id).one().id

    reject_resp = client.post(
        decide_url(res_b_id),
        headers=staff_headers,
        json={"decision": "reject", "remark": "Initial rejection"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    approve_after_reject = client.post(
        decide_url(res_b_id),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert approve_after_reject.status_code == 409


def test_redeclaration_after_decision_returns_to_pending_and_accepts_new_decision(
    client: TestClient,
    db: Session,
    world: dict,
):
    """Re-declaring after a decision returns status to pending and accepts a new decision."""
    student = make_user(db, "student_redecl", "student")
    staff_headers = headers_for(world["hostel_staff"])

    # 1. Initial declaration and decision
    client.patch(
        MY_RESIDENCE,
        headers=headers_for(student),
        json={"floor_id": world["floors"]["A1"].id},
    )
    res_id = db.query(StudentResidence).filter_by(student_id=student.id).one().id

    dec1 = client.post(
        decide_url(res_id),
        headers=staff_headers,
        json={"decision": "reject", "remark": "Wrong wing"},
    )
    assert dec1.status_code == 200
    assert dec1.json()["status"] == "rejected"

    # 2. Student re-declares to a different floor
    redecl = client.patch(
        MY_RESIDENCE,
        headers=headers_for(student),
        json={"floor_id": world["floors"]["A2"].id},
    )
    assert redecl.status_code == 200
    assert redecl.json()["status"] == "pending"
    assert redecl.json()["remark"] is None

    # Verify DB state is reset to pending
    db.expire_all()
    record = db.query(StudentResidence).filter_by(student_id=student.id).one()
    assert record.status == "pending"
    assert record.verified_by_id is None
    assert record.verified_at is None
    assert record.remark is None

    # 3. Staff can now make a new decision successfully
    dec2 = client.post(
        decide_url(record.id),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert dec2.status_code == 200
    assert dec2.json()["status"] == "verified"


def test_decision_on_unknown_id_returns_404(client: TestClient, world: dict):
    """A decision request on an unknown residence ID returns 404."""
    staff_headers = headers_for(world["hostel_staff"])
    resp = client.post(
        decide_url(999999),
        headers=staff_headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 404
