"""Residence concurrency and decision conflict tests (S3-15 carryover)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.student_residence import StudentResidence
from sprint3_hmc_world import build_world, headers_for, make_user

MY_RESIDENCE = "/api/v1/users/me/residence"
QUEUE = "/api/v1/staff/residences"


def decide_url(residence_id: int) -> str:
    return f"{QUEUE}/{residence_id}/decision"


@pytest.fixture
def world(db: Session, seeded_departments: dict, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


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
