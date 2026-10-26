"""Sprint 2 backend acceptance tests (Deep - backend tests deliverable).

These tests add NEW coverage on top of the tests already written by Dhaval and
Yashvi. They are grouped by the eight areas named in the Sprint 2 allocation:

1. Department isolation   - staff only ever see / touch their own department
2. Role guards            - student / staff / admin / anonymous access matrix
3. Invalid transitions    - illegal status changes are rejected and leave no trace
4. History atomicity      - status change + history row succeed or fail together
5. Reopen rules           - 7-day window, max 2 reopens, owner only, full cycles
6. Rolling average        - 30-day window, reopened-complaint rule, department scope
7. Feed privacy           - public complaints only, never any student identity
8. Duplicate privacy      - find_similar() only sees public + own, never the creator
                            (skipped automatically until Krish's service is merged)

Run just this file:   pytest tests/test_sprint2_deep_acceptance.py -v
"""

import importlib
import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.user import User
from app.schemas.complaint import PublicComplaintFeedItem
from app.schemas.staff import StaffComplaintStatusUpdate
from app.services import complaint_lifecycle_service as lifecycle
from app.services.complaint_lifecycle_service import (
    MAX_REOPEN_COUNT,
    REOPEN_WINDOW_DAYS,
    calculate_rolling_resolution_metrics,
    get_public_complaints_feed,
    reopen_student_complaint,
    update_department_complaint_status,
)

# --------------------------------------------------------------------------- #
# Helpers (kept local so this file does not depend on other test files)
# --------------------------------------------------------------------------- #

QUEUE_URL = "/api/v1/staff/complaints"


def _headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id), claims={"role": user.role, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _make_staff(db: Session, department_id, suffix: str = "it", is_active: bool = True) -> User:
    staff = User(
        name=f"Staff {suffix}",
        email=f"deep.staff.{suffix}@campus.edu",
        password_hash=None,
        role="staff",
        is_active=is_active,
        department_id=department_id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def _make_student(db: Session, suffix: str, name: str | None = None) -> User:
    student = User(
        name=name or f"Student {suffix.title()}",
        email=f"deep.{suffix}@student.campus.edu",
        password_hash=None,
        role="student",
        is_active=True,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def _make_complaint(
    db: Session,
    *,
    student_id: int,
    department_id: int,
    title: str = "Broken campus Wi-Fi",
    description: str = "The connection has been unavailable in the common room since this morning.",
    status: str = "submitted",
    is_public: bool = False,
    hostel: str | None = None,
    wing: str | None = None,
    floor: str | None = None,
    reopen_count: int = 0,
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> Complaint:
    created = created_at or datetime.now(timezone.utc)
    if status == "resolved" and resolved_at is None:
        resolved_at = created + timedelta(hours=1)
    complaint = Complaint(
        title=title,
        description=description,
        department_id=department_id,
        created_by_id=student_id,
        status=status,
        is_public=is_public,
        visibility_scope=("hmc_group_public" if is_public and (hostel or wing or floor) else "department_public" if is_public else "private"),
        feed_review_status=("pending" if is_public and (hostel or wing or floor) else "not_required"),
        publication_status=("pending_mapping" if is_public and (hostel or wing or floor) else "published" if is_public else "private"),
        hostel=hostel,
        wing=wing,
        floor=floor,
        reopen_count=reopen_count,
        created_at=created,
        updated_at=created,
        resolved_at=resolved_at,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def _history(db: Session, complaint_id: int) -> list[ComplaintStatusHistory]:
    return (
        db.query(ComplaintStatusHistory)
        .filter(ComplaintStatusHistory.complaint_id == complaint_id)
        .order_by(ComplaintStatusHistory.id.asc())
        .all()
    )


def _patch_status(client, complaint_id: int, headers: dict, status: str, remark: str = "Working on it."):
    return client.patch(
        f"{QUEUE_URL}/{complaint_id}/status",
        json={"status": status, "remark": remark},
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# 1. DEPARTMENT ISOLATION
# --------------------------------------------------------------------------- #


def test_department_isolation_queue_shows_only_own_department(
    client, db, seeded_departments, student_user
):
    """Each staff member's queue contains only their department's complaints."""
    it, hostel, library = seeded_departments["it"], seeded_departments["hostel"], seeded_departments["library"]
    it_ids = {
        _make_complaint(db, student_id=student_user.id, department_id=it.id, title=f"IT issue {i}").id
        for i in range(2)
    }
    hostel_id = _make_complaint(db, student_id=student_user.id, department_id=hostel.id).id
    _make_complaint(db, student_id=student_user.id, department_id=library.id)

    it_staff = _make_staff(db, it.id, "it")
    hostel_staff = _make_staff(db, hostel.id, "hostel")

    it_response = client.get(QUEUE_URL, headers=_headers(it_staff))
    assert it_response.status_code == 200
    assert {row["id"] for row in it_response.json()} == it_ids
    assert {row["department_id"] for row in it_response.json()} == {it.id}
    assert it_response.headers["X-Total-Count"] == "2"

    hostel_response = client.get(QUEUE_URL, headers=_headers(hostel_staff))
    assert [row["id"] for row in hostel_response.json()] == [hostel_id]
    assert hostel_response.headers["X-Total-Count"] == "1"


def test_department_isolation_status_filter_never_leaks_other_departments(
    client, db, seeded_departments, student_user
):
    """Filtering by status must still be scoped to the caller's department."""
    it, hostel = seeded_departments["it"], seeded_departments["hostel"]
    own_submitted = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="submitted")
    _make_complaint(db, student_id=student_user.id, department_id=it.id, status="in_progress")
    _make_complaint(db, student_id=student_user.id, department_id=hostel.id, status="submitted")

    staff = _make_staff(db, it.id, "it")
    response = client.get(f"{QUEUE_URL}?status=submitted", headers=_headers(staff))

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [own_submitted.id]
    assert response.headers["X-Total-Count"] == "1"


def test_department_isolation_foreign_complaint_is_indistinguishable_from_missing(
    client, db, seeded_departments, student_user
):
    """Another department's complaint returns the exact same 404 as a non-existent ID."""
    it, hostel = seeded_departments["it"], seeded_departments["hostel"]
    foreign = _make_complaint(db, student_id=student_user.id, department_id=hostel.id)
    staff = _make_staff(db, it.id, "it")
    headers = _headers(staff)

    missing_detail = client.get(f"{QUEUE_URL}/999999", headers=headers)
    foreign_detail = client.get(f"{QUEUE_URL}/{foreign.id}", headers=headers)
    assert missing_detail.status_code == foreign_detail.status_code == 404
    assert missing_detail.json() == foreign_detail.json()

    missing_history = client.get("/api/v1/complaints/999999/history", headers=headers)
    foreign_history = client.get(f"/api/v1/complaints/{foreign.id}/history", headers=headers)
    assert missing_history.status_code == foreign_history.status_code == 404
    assert missing_history.json() == foreign_history.json()


def test_department_isolation_cross_department_update_changes_nothing(
    client, db, seeded_departments, student_user
):
    """A blocked cross-department PATCH must not modify the complaint or write history."""
    it, hostel = seeded_departments["it"], seeded_departments["hostel"]
    foreign = _make_complaint(db, student_id=student_user.id, department_id=hostel.id, status="submitted")
    staff = _make_staff(db, it.id, "it")

    response = _patch_status(client, foreign.id, _headers(staff), "in_progress")

    assert response.status_code == 404
    db.refresh(foreign)
    assert foreign.status == "submitted"
    assert _history(db, foreign.id) == []


# --------------------------------------------------------------------------- #
# 2. ROLE GUARDS
# --------------------------------------------------------------------------- #

# (method, endpoint, role, expected HTTP status)
ROLE_GUARD_CASES = [
    ("GET", "queue", "anonymous", 401),
    ("GET", "queue", "student", 403),
    ("GET", "queue", "admin", 403),
    ("GET", "queue", "staff", 200),
    ("PATCH", "status", "anonymous", 401),
    ("PATCH", "status", "student", 403),
    ("PATCH", "status", "admin", 403),
    ("POST", "reopen", "anonymous", 401),
    ("POST", "reopen", "staff", 403),
    ("POST", "reopen", "admin", 403),
]


@pytest.mark.parametrize("method,endpoint,role,expected", ROLE_GUARD_CASES)
def test_role_guard_matrix(
    client, db, seeded_departments, student_user, student_headers, admin_headers,
    method, endpoint, role, expected,
):
    """Every role/endpoint pair returns the documented status code."""
    it = seeded_departments["it"]
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="resolved")
    staff = _make_staff(db, it.id, "it")

    headers = {
        "anonymous": {},
        "student": student_headers,
        "admin": admin_headers,
        "staff": _headers(staff),
    }[role]

    if endpoint == "queue":
        response = client.get(QUEUE_URL, headers=headers)
    elif endpoint == "status":
        response = client.patch(
            f"{QUEUE_URL}/{complaint.id}/status",
            json={"status": "in_progress", "remark": "Looking into it."},
            headers=headers,
        )
    else:
        response = client.post(f"/api/v1/complaints/{complaint.id}/reopen", json={}, headers=headers)

    assert response.status_code == expected

    if expected in (401, 403):
        # A refused request must never have changed anything.
        db.refresh(complaint)
        assert complaint.status == "resolved"
        assert _history(db, complaint.id) == []


def test_role_guard_deactivated_staff_account_is_blocked(client, db, seeded_departments):
    """A valid token for a deactivated account is rejected."""
    staff = _make_staff(db, seeded_departments["it"].id, "inactive", is_active=False)
    response = client.get(QUEUE_URL, headers=_headers(staff))
    assert response.status_code == 403


@pytest.mark.parametrize(
    "auth_header",
    ["Bearer not-a-real-token", "Bearer ", "Basic dXNlcjpwYXNz", "Bearer a.b.c"],
)
def test_role_guard_rejects_garbage_credentials(client, auth_header):
    """Malformed or forged credentials are treated as unauthenticated (401)."""
    response = client.get(QUEUE_URL, headers={"Authorization": auth_header})
    assert response.status_code == 401


def test_role_guard_token_claims_cannot_escalate_role(client, student_user):
    """The role is read from the database, so a forged 'admin' claim does not help a student."""
    forged = create_access_token(
        subject=str(student_user.id),
        claims={"role": "admin", "email": student_user.email},
    )
    response = client.get(QUEUE_URL, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# 3. INVALID TRANSITIONS
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "current,target",
    [
        ("submitted", "resolved"),     # cannot skip in_progress
        ("in_progress", "in_progress"),  # no-op transition
        ("resolved", "in_progress"),   # resolved can only go to reopened (by the student)
        ("resolved", "resolved"),
        ("reopened", "resolved"),      # reopened must pass through in_progress
    ],
)
def test_invalid_transition_is_rejected_with_409_and_leaves_no_trace(
    client, db, seeded_departments, student_user, current, target
):
    it = seeded_departments["it"]
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status=current)
    staff = _make_staff(db, it.id, "it")

    before_updated_at = complaint.updated_at
    response = _patch_status(client, complaint.id, _headers(staff), target)

    assert response.status_code == 409
    assert current in response.json()["detail"]
    db.refresh(complaint)
    assert complaint.status == current
    assert complaint.updated_at == before_updated_at
    assert _history(db, complaint.id) == []


@pytest.mark.parametrize("target", ["reopened", "submitted", "closed", "RESOLVED", ""])
def test_staff_cannot_request_statuses_outside_their_allowed_targets(
    client, db, seeded_departments, student_user, target
):
    """Staff may only target in_progress / resolved; anything else is a 422 validation error."""
    it = seeded_departments["it"]
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="in_progress")
    staff = _make_staff(db, it.id, "it")

    response = _patch_status(client, complaint.id, _headers(staff), target)

    assert response.status_code == 422
    db.refresh(complaint)
    assert complaint.status == "in_progress"
    assert _history(db, complaint.id) == []


def test_full_lifecycle_walk_records_every_step_in_order(
    client, db, seeded_departments, student_user, student_headers
):
    """submitted -> in_progress -> resolved -> reopened -> in_progress -> resolved, end to end."""
    it = seeded_departments["it"]
    staff = _make_staff(db, it.id, "it")
    staff_headers = _headers(staff)

    created = client.post(
        "/api/v1/complaints",
        json={
            "title": "Lab computers cannot connect",
            "description": "None of the lab computers can reach the campus network today.",
            "department_id": it.id,
        },
        headers=student_headers,
    )
    assert created.status_code == 201
    complaint_id = created.json()["id"]

    assert _patch_status(client, complaint_id, staff_headers, "in_progress", "Assigned.").status_code == 200
    assert _patch_status(client, complaint_id, staff_headers, "resolved", "Router replaced.").status_code == 200
    reopened = client.post(
        f"/api/v1/complaints/{complaint_id}/reopen",
        json={"remark": "It is down again."},
        headers=student_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    assert _patch_status(client, complaint_id, staff_headers, "in_progress", "Back on it.").status_code == 200
    final = _patch_status(client, complaint_id, staff_headers, "resolved", "Fixed properly.")
    assert final.status_code == 200
    assert final.json()["reopen_count"] == 1

    history = client.get(f"/api/v1/complaints/{complaint_id}/history", headers=student_headers)
    assert history.status_code == 200
    events = history.json()

    assert [(e["from_status"], e["to_status"]) for e in events] == [
        (None, "submitted"),
        ("submitted", "in_progress"),
        ("in_progress", "resolved"),
        ("resolved", "reopened"),
        ("reopened", "in_progress"),
        ("in_progress", "resolved"),
    ]
    assert [e["actor_id"] for e in events] == [
        student_user.id, staff.id, staff.id, student_user.id, staff.id, staff.id,
    ]
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)


# --------------------------------------------------------------------------- #
# 4. HISTORY ATOMICITY
# --------------------------------------------------------------------------- #


def test_status_change_and_history_row_are_saved_in_one_commit(
    db, seeded_departments, student_user, monkeypatch
):
    """At the moment of the single commit, BOTH the status edit and the history row are pending."""
    it = seeded_departments["it"]
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="submitted")
    staff = _make_staff(db, it.id, "it")

    real_commit = db.commit
    snapshots = []

    def spy_commit():
        snapshots.append(
            {
                "history_pending": any(isinstance(obj, ComplaintStatusHistory) for obj in db.new),
                "status_in_transaction": db.query(Complaint.status).filter(Complaint.id == complaint.id).scalar(),
            }
        )
        return real_commit()

    monkeypatch.setattr(db, "commit", spy_commit)

    update_department_complaint_status(
        db, staff, complaint.id, StaffComplaintStatusUpdate(status="in_progress", remark="Assigned to IT.")
    )

    assert len(snapshots) == 1, "status update must use exactly one commit"
    assert snapshots[0] == {"history_pending": True, "status_in_transaction": "in_progress"}
    rows = _history(db, complaint.id)
    assert [(r.from_status, r.to_status, r.actor_id) for r in rows] == [("submitted", "in_progress", staff.id)]


def test_failed_history_write_means_status_change_is_never_saved(
    db, seeded_departments, student_user, monkeypatch
):
    """A failed history write rolls back the status update."""
    it = seeded_departments["it"]
    complaint = _make_complaint(
        db, student_id=student_user.id,
        department_id=it.id, status="submitted",
    )
    staff = _make_staff(db, it.id, "it")

    work_db = Session(
        bind=db.connection(),
        join_transaction_mode="create_savepoint",
    )

    def broken_history(*args, **kwargs):
        raise RuntimeError("simulated history failure")

    def forbidden_commit():
        raise AssertionError(
            "commit must not be reached when history creation fails"
        )

    monkeypatch.setattr(lifecycle, "ComplaintStatusHistory", broken_history)
    monkeypatch.setattr(work_db, "commit", forbidden_commit)

    try:
        with pytest.raises(RuntimeError, match="simulated history failure"):
            update_department_complaint_status(
                work_db,
                staff,
                complaint.id,
                StaffComplaintStatusUpdate(
                    status="in_progress",
                    remark="Assigned.",
                ),
            )
    finally:
        work_db.close()

    db.refresh(complaint)
    assert complaint.status == "submitted"
    assert _history(db, complaint.id) == []

def test_failed_history_write_during_reopen_leaves_complaint_resolved(
    db, seeded_departments, student_user, monkeypatch
):
    """A failed reopen history write leaves the complaint resolved."""
    it = seeded_departments["it"]
    complaint = _make_complaint(
        db, student_id=student_user.id,
        department_id=it.id, status="resolved",
    )

    work_db = Session(
        bind=db.connection(),
        join_transaction_mode="create_savepoint",
    )

    def broken_history(*args, **kwargs):
        raise RuntimeError("simulated history failure")

    def forbidden_commit():
        raise AssertionError(
            "commit must not be reached when history creation fails"
        )

    monkeypatch.setattr(lifecycle, "ComplaintStatusHistory", broken_history)
    monkeypatch.setattr(work_db, "commit", forbidden_commit)

    try:
        with pytest.raises(RuntimeError, match="simulated history failure"):
            reopen_student_complaint(
                work_db,
                student_user,
                complaint.id,
                remark="Back again.",
            )
    finally:
        work_db.close()

    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
    assert complaint.resolved_at is not None
    assert _history(db, complaint.id) == []

def test_new_complaint_gets_exactly_one_initial_history_row(
    client, db, seeded_departments, student_user, student_headers
):
    """Creating a complaint writes the complaint and its 'submitted' history event together."""
    response = client.post(
        "/api/v1/complaints",
        json={
            "title": "Mess food quality",
            "description": "The dinner served yesterday was not fresh and several students felt unwell.",
            "department_id": seeded_departments["hostel"].id,
        },
        headers=student_headers,
    )
    assert response.status_code == 201

    rows = _history(db, response.json()["id"])
    assert len(rows) == 1
    assert (rows[0].from_status, rows[0].to_status, rows[0].actor_id) == (None, "submitted", student_user.id)


# --------------------------------------------------------------------------- #
# 5. REOPEN RULES
# --------------------------------------------------------------------------- #


def test_reopen_window_boundary_just_inside_allowed_just_outside_rejected(
    client, db, seeded_departments, student_user, student_headers
):
    it = seeded_departments["it"]
    now = datetime.now(timezone.utc)
    inside = _make_complaint(
        db, student_id=student_user.id, department_id=it.id, status="resolved",
        created_at=now - timedelta(days=9),
        resolved_at=now - timedelta(days=REOPEN_WINDOW_DAYS) + timedelta(hours=1),
    )
    outside = _make_complaint(
        db, student_id=student_user.id, department_id=it.id, status="resolved",
        created_at=now - timedelta(days=9),
        resolved_at=now - timedelta(days=REOPEN_WINDOW_DAYS) - timedelta(hours=1),
    )

    ok = client.post(f"/api/v1/complaints/{inside.id}/reopen", json={}, headers=student_headers)
    too_late = client.post(f"/api/v1/complaints/{outside.id}/reopen", json={}, headers=student_headers)

    assert ok.status_code == 200
    assert too_late.status_code == 400
    assert "window" in too_late.json()["detail"].lower()
    db.refresh(outside)
    assert outside.status == "resolved"
    assert outside.reopen_count == 0
    assert _history(db, outside.id) == []


def test_reopen_limit_is_enforced_across_complete_cycles(
    client, db, seeded_departments, student_user, student_headers
):
    """After MAX_REOPEN_COUNT full reopen->resolve cycles the next reopen is refused."""
    it = seeded_departments["it"]
    staff_headers = _headers(_make_staff(db, it.id, "it"))
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="resolved")
    reopen_url = f"/api/v1/complaints/{complaint.id}/reopen"

    for cycle in range(1, MAX_REOPEN_COUNT + 1):
        reopened = client.post(reopen_url, json={}, headers=student_headers)
        assert reopened.status_code == 200, f"cycle {cycle} reopen should succeed"
        assert reopened.json()["reopen_count"] == cycle
        assert _patch_status(client, complaint.id, staff_headers, "in_progress").status_code == 200
        assert _patch_status(client, complaint.id, staff_headers, "resolved").status_code == 200

    refused = client.post(reopen_url, json={}, headers=student_headers)
    assert refused.status_code == 400
    assert "maximum" in refused.json()["detail"].lower()

    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == MAX_REOPEN_COUNT
    # 3 events per cycle (reopened, in_progress, resolved); the refused attempt wrote nothing.
    assert len(_history(db, complaint.id)) == 3 * MAX_REOPEN_COUNT


@pytest.mark.parametrize("current_status", ["submitted", "in_progress", "reopened"])
def test_only_resolved_complaints_can_be_reopened(
    client, db, seeded_departments, student_user, student_headers, current_status
):
    complaint = _make_complaint(
        db, student_id=student_user.id, department_id=seeded_departments["it"].id, status=current_status
    )

    response = client.post(f"/api/v1/complaints/{complaint.id}/reopen", json={}, headers=student_headers)

    assert response.status_code == 409
    db.refresh(complaint)
    assert complaint.status == current_status
    assert complaint.reopen_count == 0
    assert _history(db, complaint.id) == []


def test_only_the_owner_can_reopen_and_other_students_change_nothing(
    client, db, seeded_departments, student_user
):
    other = _make_student(db, "intruder")
    complaint = _make_complaint(
        db, student_id=student_user.id, department_id=seeded_departments["it"].id, status="resolved"
    )

    response = client.post(f"/api/v1/complaints/{complaint.id}/reopen", json={}, headers=_headers(other))

    assert response.status_code == 404
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
    assert _history(db, complaint.id) == []


def test_reopened_complaint_is_marked_for_staff_with_cleared_resolution_time(
    client, db, seeded_departments, student_user, student_headers
):
    it = seeded_departments["it"]
    staff_headers = _headers(_make_staff(db, it.id, "it"))
    complaint = _make_complaint(db, student_id=student_user.id, department_id=it.id, status="resolved")

    assert client.post(
        f"/api/v1/complaints/{complaint.id}/reopen", json={"remark": "Still broken."}, headers=student_headers
    ).status_code == 200

    queue = client.get(f"{QUEUE_URL}?status=reopened", headers=staff_headers)
    assert [row["id"] for row in queue.json()] == [complaint.id]
    assert queue.json()[0]["resolved_at"] is None

    detail = client.get(f"{QUEUE_URL}/{complaint.id}", headers=staff_headers).json()
    assert detail["status"] == "reopened"
    assert detail["reopen_count"] == 1
    assert detail["resolved_at"] is None


# --------------------------------------------------------------------------- #
# 6. ROLLING AVERAGE (resolution time)
#
# Rule being tested (as implemented in calculate_rolling_resolution_metrics):
#   duration = resolved_at - created_at, only for complaints whose resolved_at is
#   inside the last `window_days` (default 30). A reopened complaint has
#   resolved_at = NULL, so it is excluded until it is resolved again; its new
#   duration is then measured from the ORIGINAL created_at.
# --------------------------------------------------------------------------- #


def _resolved_with_duration(db, student_id, department_id, *, hours: float, resolved_days_ago: float = 1):
    resolved_at = datetime.now(timezone.utc) - timedelta(days=resolved_days_ago)
    return _make_complaint(
        db, student_id=student_id, department_id=department_id, status="resolved",
        created_at=resolved_at - timedelta(hours=hours), resolved_at=resolved_at,
    )


def test_rolling_average_is_the_mean_of_resolved_minus_created_in_hours(
    db, seeded_departments, student_user
):
    it = seeded_departments["it"]
    for hours in (10, 20, 30):
        _resolved_with_duration(db, student_user.id, it.id, hours=hours)

    metrics = calculate_rolling_resolution_metrics(db, department_id=it.id)

    assert metrics["resolved_count"] == 3
    assert metrics["average_resolution_hours"] == 20.0
    assert metrics["average_resolution_days"] == round(20 / 24, 2)
    assert metrics["median_resolution_hours"] == 20.0
    assert metrics["min_resolution_hours"] == 10.0
    assert metrics["max_resolution_hours"] == 30.0


def test_rolling_average_only_includes_the_last_30_days(db, seeded_departments, student_user):
    it = seeded_departments["it"]
    _resolved_with_duration(db, student_user.id, it.id, hours=10, resolved_days_ago=29)  # inside window
    _resolved_with_duration(db, student_user.id, it.id, hours=100, resolved_days_ago=31)  # outside window

    default_window = calculate_rolling_resolution_metrics(db, department_id=it.id)
    assert default_window["window_days"] == 30
    assert default_window["resolved_count"] == 1
    assert default_window["average_resolution_hours"] == 10.0

    short_window = calculate_rolling_resolution_metrics(db, window_days=7, department_id=it.id)
    assert short_window["resolved_count"] == 0
    assert short_window["average_resolution_hours"] is None

    long_window = calculate_rolling_resolution_metrics(db, window_days=60, department_id=it.id)
    assert long_window["resolved_count"] == 2
    assert long_window["average_resolution_hours"] == 55.0


def test_rolling_average_ignores_complaints_that_are_not_resolved(db, seeded_departments, student_user):
    it = seeded_departments["it"]
    long_ago = datetime.now(timezone.utc) - timedelta(days=5)
    for status in ("submitted", "in_progress", "reopened"):
        _make_complaint(db, student_id=student_user.id, department_id=it.id, status=status, created_at=long_ago)
    _resolved_with_duration(db, student_user.id, it.id, hours=8)

    metrics = calculate_rolling_resolution_metrics(db, department_id=it.id)

    assert metrics["resolved_count"] == 1
    assert metrics["average_resolution_hours"] == 8.0


def test_rolling_average_reopened_rule_excluded_while_open_then_measured_from_creation(
    db, seeded_departments, student_user
):
    it = seeded_departments["it"]
    staff = _make_staff(db, it.id, "it")
    complaint = _make_complaint(
        db, student_id=student_user.id, department_id=it.id, status="in_progress",
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )

    update_department_complaint_status(
        db, staff, complaint.id, StaffComplaintStatusUpdate(status="resolved", remark="Fixed.")
    )
    first = calculate_rolling_resolution_metrics(db, department_id=it.id)
    assert first["resolved_count"] == 1
    assert first["average_resolution_hours"] == pytest.approx(48.0, abs=0.05)

    reopen_student_complaint(db, student_user, complaint.id, remark="Broke again.")
    while_reopened = calculate_rolling_resolution_metrics(db, department_id=it.id)
    assert while_reopened["resolved_count"] == 0
    assert while_reopened["average_resolution_hours"] is None

    update_department_complaint_status(
        db, staff, complaint.id, StaffComplaintStatusUpdate(status="in_progress", remark="Re-checking.")
    )
    update_department_complaint_status(
        db, staff, complaint.id, StaffComplaintStatusUpdate(status="resolved", remark="Fixed for good.")
    )
    final = calculate_rolling_resolution_metrics(db, department_id=it.id)
    assert final["resolved_count"] == 1
    assert final["average_resolution_hours"] == pytest.approx(48.0, abs=0.05)


def test_rolling_average_department_filter_and_negative_durations(db, seeded_departments, student_user):
    it, hostel = seeded_departments["it"], seeded_departments["hostel"]
    _resolved_with_duration(db, student_user.id, it.id, hours=10)
    _resolved_with_duration(db, student_user.id, hostel.id, hours=50)
    # Corrupt data: resolved BEFORE it was created -> must be ignored, not averaged in.
    now = datetime.now(timezone.utc)
    _make_complaint(
        db, student_id=student_user.id, department_id=it.id, status="resolved",
        created_at=now, resolved_at=now - timedelta(hours=5),
    )

    assert calculate_rolling_resolution_metrics(db, department_id=it.id)["average_resolution_hours"] == 10.0
    assert calculate_rolling_resolution_metrics(db, department_id=hostel.id)["average_resolution_hours"] == 50.0
    overall = calculate_rolling_resolution_metrics(db)
    assert overall["resolved_count"] == 2
    assert overall["average_resolution_hours"] == 30.0


# --------------------------------------------------------------------------- #
# 7. FEED PRIVACY
# --------------------------------------------------------------------------- #

FORBIDDEN_IDENTITY_KEYS = {
    "created_by_id", "created_by", "creator", "student", "student_id", "student_name",
    "student_email", "email", "user", "user_id", "owner", "owner_id", "roll_number", "phone",
}


def test_hmc_scoped_public_complaints_are_not_returned_by_department_feed(db, seeded_departments, student_user):
    it = seeded_departments["it"]
    hmc_public = _make_complaint(
        db, student_id=student_user.id, department_id=it.id, is_public=True,
        hostel="legacy text", wing="A", floor="3", title="Pending HMC issue",
    )
    _make_complaint(
        db, student_id=student_user.id, department_id=it.id, is_public=False,
        hostel="legacy text", wing="A", floor="3", title="Private issue",
    )
    items, total = get_public_complaints_feed(db)
    assert hmc_public.id not in {item.id for item in items}
    assert all(item.visibility_scope == "department_public" for item in items)
    assert total == len(items)


def test_feed_total_count_and_pagination_exclude_private_complaints(db, seeded_departments, student_user):
    it = seeded_departments["it"]
    for i in range(3):
        _make_complaint(db, student_id=student_user.id, department_id=it.id, is_public=True, title=f"Public {i}")
    for i in range(4):
        _make_complaint(db, student_id=student_user.id, department_id=it.id, is_public=False, title=f"Private {i}")

    page, total = get_public_complaints_feed(db, limit=2, offset=0)
    assert total == 3
    assert len(page) == 2

    last_page, total_again = get_public_complaints_feed(db, limit=2, offset=2)
    assert total_again == 3
    assert len(last_page) == 1
    assert {c.id for c in page}.isdisjoint({c.id for c in last_page})


def test_feed_payload_contains_no_student_identity(db, seeded_departments):
    student = _make_student(db, "privacy", name="Priya Privacytest")
    _make_complaint(
        db, student_id=student.id, department_id=seeded_departments["it"].id, is_public=True,
        title="Campus common-area water cooler not working",
    )

    items, _ = get_public_complaints_feed(db)
    # department_name lives on the related Department row, so build each item the way a route would.
    payload = [
        PublicComplaintFeedItem.model_validate(
            {
                **{name: getattr(item, name) for name in PublicComplaintFeedItem.model_fields if name != "department_name"},
                "department_name": item.department.name,
            }
        ).model_dump(mode="json")
        for item in items
    ]

    assert len(payload) == 1
    assert FORBIDDEN_IDENTITY_KEYS.isdisjoint(payload[0].keys())
    assert FORBIDDEN_IDENTITY_KEYS.isdisjoint(PublicComplaintFeedItem.model_fields.keys())
    serialized = json.dumps(payload)
    assert student.email not in serialized
    assert "Priya" not in serialized and "Privacytest" not in serialized


def test_feed_hides_a_complaint_as_soon_as_it_is_made_private(db, seeded_departments, student_user):
    complaint = _make_complaint(
        db, student_id=student_user.id, department_id=seeded_departments["it"].id, is_public=True
    )
    assert [c.id for c in get_public_complaints_feed(db)[0]] == [complaint.id]

    complaint.is_public = False
    complaint.visibility_scope = "private"
    complaint.feed_review_status = "not_required"
    db.commit()

    items, total = get_public_complaints_feed(db)
    assert items == []
    assert total == 0


# --------------------------------------------------------------------------- #
# 8. DUPLICATE PRIVACY
#
# The TF-IDF duplicate service (Krish) is not merged yet. These tests look for
# `find_similar` in the likely module names and SKIP with a clear reason until
# it exists. Once Krish's PR is merged they run automatically; if his function
# signature differs, only the small adapter below needs adjusting.
# --------------------------------------------------------------------------- #

DUPLICATE_MODULE_CANDIDATES = (
    "app.services.duplicate_service",
    "app.services.duplicate_suggestion_service",
    "app.services.duplicate_detection_service",
    "app.services.duplicate_suggestions",
    "app.services.similarity_service",
)
ALLOWED_DUPLICATE_KEYS = {
    "id", "complaint_id", "title", "department", "department_id", "department_name",
    "status", "score", "similarity", "similarity_score",
}


def _load_find_similar():
    for module_name in DUPLICATE_MODULE_CANDIDATES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise  # a real missing dependency inside the module: do not hide it
        function = getattr(module, "find_similar", None)
        if callable(function):
            return function
    pytest.skip("Duplicate-suggestion service (find_similar) is not merged yet - see Krish's task.")


def _call_find_similar(function, db: Session, student: User, title: str, description: str) -> list[dict]:
    values = {
        "db": db, "session": db, "student": student, "user": student, "current_user": student,
        "student_id": student.id, "user_id": student.id, "requester_id": student.id,
        "title": title, "description": description,
    }
    kwargs = {}
    for name, parameter in inspect.signature(function).parameters.items():
        if name in values:
            kwargs[name] = values[name]
        elif parameter.default is inspect.Parameter.empty and parameter.kind in (
            parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY,
        ):
            pytest.skip(f"find_similar has an unexpected required parameter '{name}'; adjust the adapter.")
    results = function(**kwargs)
    return [_as_dict(item) for item in results]


def _as_dict(item) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return dict(vars(item))


SIMILAR_TEXT = "Hostel wifi router is down on the second floor and nobody can connect to the internet"


def test_duplicate_suggestions_only_come_from_public_or_own_complaints(db, seeded_departments, student_user):
    find_similar = _load_find_similar()
    hostel = seeded_departments["hostel"]
    other = _make_student(db, "other")
    third = _make_student(db, "third")
    _make_complaint(db, student_id=other.id, department_id=hostel.id, is_public=False,
                    title="OTHERPRIVATE wifi router down", description=SIMILAR_TEXT)
    _make_complaint(db, student_id=third.id, department_id=hostel.id, is_public=True,
                    title="THIRDPUBLIC wifi router down", description=SIMILAR_TEXT)
    _make_complaint(db, student_id=student_user.id, department_id=hostel.id, is_public=False,
                    title="OWNPRIVATE wifi router down", description=SIMILAR_TEXT)

    titles = [r["title"] for r in _call_find_similar(find_similar, db, student_user, "Wifi router down", SIMILAR_TEXT)]

    assert not any("OTHERPRIVATE" in t for t in titles), "another student's private complaint leaked"
    assert any("THIRDPUBLIC" in t for t in titles)
    assert any("OWNPRIVATE" in t for t in titles)


def test_duplicate_suggestions_never_expose_the_creator(db, seeded_departments, student_user):
    find_similar = _load_find_similar()
    other = _make_student(db, "creator", name="Chirag Creatortest")
    _make_complaint(db, student_id=other.id, department_id=seeded_departments["hostel"].id, is_public=True,
                    title="Wifi router down", description=SIMILAR_TEXT)

    results = _call_find_similar(find_similar, db, student_user, "Wifi router down", SIMILAR_TEXT)

    assert results, "expected at least one similar public complaint"
    for result in results:
        assert FORBIDDEN_IDENTITY_KEYS.isdisjoint(result.keys()), result.keys()
        assert set(result.keys()) <= ALLOWED_DUPLICATE_KEYS, result.keys()
    serialized = json.dumps(results, default=str)
    assert other.email not in serialized
    assert "Chirag" not in serialized and "Creatortest" not in serialized


def test_duplicate_suggestions_return_at_most_three_matches(db, seeded_departments, student_user):
    find_similar = _load_find_similar()
    other = _make_student(db, "many")
    for i in range(5):
        _make_complaint(db, student_id=other.id, department_id=seeded_departments["hostel"].id, is_public=True,
                        title=f"Wifi router down {i}", description=SIMILAR_TEXT)

    results = _call_find_similar(find_similar, db, student_user, "Wifi router down", SIMILAR_TEXT)

    assert 1 <= len(results) <= 3
