"""Acceptance tests for staff queue/detail routes and lifecycle handoff boundary."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.user import User


def _staff_with_department(db: Session, department_id: int, suffix: str = "it") -> tuple[User, dict[str, str]]:
    staff = User(
        name=f"Staff {suffix}",
        email=f"staff.{suffix}@campus.edu",
        password_hash=None,
        role="staff",
        is_active=True,
        department_id=department_id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    token = create_access_token(subject=str(staff.id), claims={"role": staff.role, "email": staff.email})
    return staff, {"Authorization": f"Bearer {token}"}


def _complaint(
    db: Session,
    *,
    department_id: int,
    created_by_id: int,
    title: str = "Broken campus Wi-Fi",
    status: str = "submitted",
    created_at: datetime | None = None,
    reopen_count: int = 0,
    resolved_at: datetime | None = None,
) -> Complaint:
    complaint = Complaint(
        title=title,
        description="The connection has been unavailable in the common room since this morning.",
        department_id=department_id,
        created_by_id=created_by_id,
        status=status,
        is_public=False,
        created_at=created_at,
        updated_at=created_at,
        reopen_count=reopen_count,
        resolved_at=resolved_at,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def _seed_department_complaint(db, seeded_departments, student_user, **kwargs):
    return _complaint(
        db,
        department_id=seeded_departments[kwargs.pop("department", "it")].id,
        created_by_id=student_user.id,
        **kwargs,
    )


def test_staff_queue_is_department_scoped(client, db, seeded_departments, student_user):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    own = _seed_department_complaint(db, seeded_departments, student_user, title="Own department issue")
    _seed_department_complaint(
        db,
        seeded_departments,
        student_user,
        department="hostel",
        title="Other department issue",
    )

    response = client.get("/api/v1/staff/complaints", headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [own.id]
    assert response.headers["X-Total-Count"] == "1"
    assert "created_by_id" not in response.json()[0]


def test_staff_queue_status_filter(client, db, seeded_departments, student_user):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    submitted = _seed_department_complaint(db, seeded_departments, student_user, title="Submitted issue")
    _seed_department_complaint(db, seeded_departments, student_user, title="Active issue", status="in_progress")

    response = client.get("/api/v1/staff/complaints?status=in_progress", headers=headers)

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Active issue"]
    assert response.headers["X-Total-Count"] == "1"
    assert submitted.id not in [item["id"] for item in response.json()]


def test_staff_queue_pagination_and_count(client, db, seeded_departments, student_user):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    base = datetime(2026, 10, 20, tzinfo=timezone.utc)
    for i in range(3):
        _seed_department_complaint(
            db,
            seeded_departments,
            student_user,
            title=f"Issue {i}",
            created_at=base + timedelta(minutes=i),
        )

    response = client.get("/api/v1/staff/complaints?limit=2&offset=1", headers=headers)

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "3"
    assert [item["title"] for item in response.json()] == ["Issue 1", "Issue 0"]


def test_staff_queue_validates_pagination(client, db, seeded_departments):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    assert client.get("/api/v1/staff/complaints?limit=101", headers=headers).status_code == 422
    assert client.get("/api/v1/staff/complaints?offset=-1", headers=headers).status_code == 422


def test_staff_can_view_complaint_in_own_department(client, db, seeded_departments, student_user):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    response = client.get(f"/api/v1/staff/complaints/{complaint.id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == complaint.id
    assert data["description"] == complaint.description
    assert data["department_id"] == seeded_departments["it"].id
    assert data["department_name"] == "IT Services"
    assert data["status"] == "submitted"
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert "password_hash" not in data
    assert "created_by_id" not in data


def test_staff_gets_same_404_for_cross_department_complaint(client, db, seeded_departments, student_user):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    other = _seed_department_complaint(db, seeded_departments, student_user, department="hostel")

    response = client.get(f"/api/v1/staff/complaints/{other.id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Complaint not found."


def test_staff_detail_nonexistent_complaint_is_404(client, db, seeded_departments):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    response = client.get("/api/v1/staff/complaints/2147483647", headers=headers)
    assert response.status_code == 404


def test_staff_detail_requires_positive_id(client, staff_headers):
    response = client.get("/api/v1/staff/complaints/0", headers=staff_headers)
    assert response.status_code == 422


def test_student_is_forbidden_from_staff_queue(client, student_headers):
    response = client.get("/api/v1/staff/complaints", headers=student_headers)
    assert response.status_code == 403


def test_staff_without_department_is_forbidden(client, staff_headers):
    response = client.get("/api/v1/staff/complaints", headers=staff_headers)
    assert response.status_code == 403



def test_student_is_forbidden_from_staff_status_update(client, student_headers):
    response = client.patch(
        "/api/v1/staff/complaints/1/status",
        json={"status": "in_progress", "remark": "Start investigation."},
        headers=student_headers,
    )
    assert response.status_code == 403


def test_status_update_for_another_department_returns_404(
    client, db, seeded_departments, student_user
):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(
        db, seeded_departments, student_user, department="hostel"
    )

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "in_progress", "remark": "Must remain private."},
        headers=headers,
    )

    assert response.status_code == 404
    db.refresh(complaint)
    assert complaint.status == "submitted"
    assert db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).count() == 0


def test_status_update_moves_submitted_to_in_progress(
    client, db, seeded_departments, student_user
):
    staff, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "in_progress", "remark": "Start investigation."},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == complaint.id
    assert data["status"] == "in_progress"
    assert data["department_id"] == seeded_departments["it"].id

    db.refresh(complaint)
    assert complaint.status == "in_progress"

    history = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(history) == 1
    assert history[0].from_status == "submitted"
    assert history[0].to_status == "in_progress"
    assert history[0].actor_id == staff.id
    assert history[0].remark == "Start investigation."


def test_status_update_moves_in_progress_to_resolved(
    client, db, seeded_departments, student_user
):
    staff, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(
        db, seeded_departments, student_user, status="in_progress"
    )

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "resolved", "remark": "Replaced faulty router."},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None

    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.resolved_at is not None

    history = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(history) == 1
    assert history[0].from_status == "in_progress"
    assert history[0].to_status == "resolved"
    assert history[0].actor_id == staff.id
    assert history[0].remark == "Replaced faulty router."


def test_status_update_rejects_disallowed_transition_with_409(
    client, db, seeded_departments, student_user
):
    staff, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    # Directly skipping from submitted to resolved is not allowed by the state machine
    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "resolved", "remark": "Try to resolve directly."},
        headers=headers,
    )

    assert response.status_code == 409
    assert "invalid status transition" in response.json()["detail"].lower()
    db.refresh(complaint)
    assert complaint.status == "submitted"
    assert db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).count() == 0


@pytest.mark.parametrize("status_value", ["reopened", "submitted", "invalid"])
def test_status_update_rejects_invalid_staff_target(
    client, db, seeded_departments, student_user, status_value
):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": status_value, "remark": "Invalid target."},
        headers=headers,
    )

    assert response.status_code == 422
    db.refresh(complaint)
    assert complaint.status == "submitted"


@pytest.mark.parametrize("remark", ["", "   ", "\n\t"])
def test_blank_status_remarks_are_rejected(
    client, db, seeded_departments, student_user, remark
):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "in_progress", "remark": remark},
        headers=headers,
    )

    assert response.status_code == 422
    db.refresh(complaint)
    assert complaint.status == "submitted"


def test_status_remark_maximum_length_is_enforced(
    client, db, seeded_departments, student_user
):
    _, headers = _staff_with_department(db, seeded_departments["it"].id)
    complaint = _seed_department_complaint(db, seeded_departments, student_user)

    response = client.patch(
        f"/api/v1/staff/complaints/{complaint.id}/status",
        json={"status": "in_progress", "remark": "x" * 2001},
        headers=headers,
    )

    assert response.status_code == 422
    db.refresh(complaint)
    assert complaint.status == "submitted"
