"""True concurrency test for residence decisions (review fix for PR #76).

Two staff decide the same pending residence at the same moment, each with its own
database session and connection. Exactly one decision may win; the other must get
409 and must not change anything.

Runs on PostgreSQL when CCMS_DISPOSABLE_TEST_POSTGRES_URL points at a dedicated local
test database (as in the PostgreSQL CI job). Otherwise it runs on a temporary SQLite file.
"""

import os
import tempfile
import threading
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.main import app
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.residence import ResidenceDecision
from app.services.residence_service import decide_residence
from sprint3_hmc_world import build_world, headers_for, make_user, set_residence

MY_RESIDENCE = "/api/v1/users/me/residence"
QUEUE = "/api/v1/staff/residences"

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def decide_url(residence_id: int) -> str:
    return f"{QUEUE}/{residence_id}/decision"


@pytest.fixture
def world(db: Session, seeded_departments: dict, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


def _postgres_url_problem(raw_url: str) -> str | None:
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        return "not a postgresql URL"
    if {"host", "hostaddr", "service"} & {key.lower() for key in url.query}:
        return "host/hostaddr/service query parameters are not allowed"
    if (url.host or "").lower() not in LOOPBACK_HOSTS:
        return f"host {url.host!r} is not a loopback address"
    if "test" not in (url.database or "").lower():
        return "database name must contain 'test'"
    return None


@pytest.fixture
def race_engine():
    """Engine for a private database that several sessions can use at once."""
    pg_url = os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL")
    if pg_url:
        problem = _postgres_url_problem(pg_url)
        if problem:
            pytest.fail(f"Refusing to use CCMS_DISPOSABLE_TEST_POSTGRES_URL: {problem}")
        schema = f"race_{uuid.uuid4().hex[:10]}"
        admin = create_engine(pg_url)
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            pg_url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=5
        )
        Base.metadata.create_all(bind=engine)
        yield engine
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
    else:
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        engine = create_engine(
            f"sqlite:///{handle.name}", connect_args={"timeout": 30, "check_same_thread": False}
        )
        Base.metadata.create_all(bind=engine)
        yield engine
        engine.dispose()
        os.unlink(handle.name)


def _seed(session_factory) -> dict:
    """Create a pending residence and two staff members; return plain ids."""
    with session_factory() as db:
        departments = {
            "hostel": Department(name="Hostel", description="Hostel", is_active=True),
            "it": Department(name="IT Services", description="IT", is_active=True),
        }
        db.add_all(departments.values())
        db.commit()
        for dept in departments.values():
            db.refresh(dept)
        alice = make_user(db, "race_alice", "student")
        bob = make_user(db, "race_bob", "student")
        world = build_world(db, departments, alice, bob)
        second_staff = make_user(db, "race_staff_2", "staff", departments["hostel"].id)

        # Hostel staff only see residences in hostels they are assigned to.
        admin = make_user(db, "race_admin", "admin")
        for staff in (world["hostel_staff"], second_staff):
            exists = db.query(StaffHostelAssignment).filter_by(user_id=staff.id, hostel_id=world["main"].id).first()
            if exists is None:
                db.add(StaffHostelAssignment(user_id=staff.id, hostel_id=world["main"].id, assigned_by_id=admin.id))
        db.commit()

        residence = db.query(StudentResidence).filter_by(student_id=alice.id).one()
        residence.status = "pending"
        residence.verified_by_id = None
        residence.verified_at = None
        residence.remark = None
        db.commit()
        return {
            "residence_id": residence.id,
            "staff_ids": [world["hostel_staff"].id, second_staff.id],
        }


def test_postgresql_two_simultaneous_decisions_one_succeeds_one_gets_409(race_engine):
    session_factory = sessionmaker(bind=race_engine, autoflush=False, expire_on_commit=False)
    ids = _seed(session_factory)

    barrier = threading.Barrier(2)
    outcomes: list = [None, None]
    decisions = [
        ResidenceDecision(decision="approve", remark="approved by staff one"),
        ResidenceDecision(decision="reject", remark="rejected by staff two"),
    ]

    def worker(index: int) -> None:
        # Each thread has its own session, and so its own connection and transaction.
        with session_factory() as db:
            reviewer = db.get(User, ids["staff_ids"][index])
            barrier.wait(timeout=10)  # both threads fire together
            try:
                result = decide_residence(db, reviewer, ids["residence_id"], decisions[index])
                outcomes[index] = ("ok", result.status)
            except HTTPException as exc:
                db.rollback()
                outcomes[index] = ("http", exc.status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads), "a decision request hung"

    successes = [o for o in outcomes if o and o[0] == "ok"]
    conflicts = [o for o in outcomes if o and o == ("http", 409)]
    assert len(successes) == 1, outcomes
    assert len(conflicts) == 1, outcomes

    # The stored row reflects only the winning decision.
    winner_index = next(i for i, o in enumerate(outcomes) if o[0] == "ok")
    with session_factory() as db:
        row = db.get(StudentResidence, ids["residence_id"])
        assert row.status == ("verified" if winner_index == 0 else "rejected")
        assert row.remark == decisions[winner_index].remark
        assert row.verified_by_id == ids["staff_ids"][winner_index]
        assert row.verified_at is not None


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
