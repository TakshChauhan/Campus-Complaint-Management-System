"""API tests for student complaint reopening."""

from datetime import datetime, timedelta, timezone

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory


def _resolved_complaint(
    db,
    *,
    student_id: int,
    department_id: int,
    reopen_count: int = 0,
    resolved_at: datetime | None = None,
    status: str = "resolved",
) -> Complaint:
    now = datetime.now(timezone.utc)
    complaint = Complaint(
        title="Hostel Wi-Fi keeps dropping",
        description="The connection repeatedly drops in the hostel common room.",
        department_id=department_id,
        created_by_id=student_id,
        status=status,
        is_public=False,
        created_at=now - timedelta(days=2),
        updated_at=now,
        resolved_at=resolved_at if resolved_at is not None else now - timedelta(hours=12),
        reopen_count=reopen_count,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def test_student_can_reopen_own_resolved_complaint_and_history_is_written(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )

    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={"remark": "The Wi-Fi issue returned this morning."},
        headers=student_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == complaint.id
    assert data["status"] == "reopened"
    assert data["reopen_count"] == 1
    assert data["resolved_at"] is None
    assert data["updated_at"] is not None

    db.refresh(complaint)
    assert complaint.status == "reopened"
    assert complaint.reopen_count == 1
    assert complaint.resolved_at is None

    events = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(events) == 1
    assert events[0].from_status == "resolved"
    assert events[0].to_status == "reopened"
    assert events[0].actor_id == student_user.id
    assert events[0].remark == "The Wi-Fi issue returned this morning."


def test_student_can_reopen_without_request_body_and_default_remark_is_recorded(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )

    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        headers=student_headers,
    )

    assert response.status_code == 200
    event = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).one()
    assert event.remark == "Student requested complaint reopen."


def test_reopen_rejects_non_owner_without_mutating_complaint(
    client, db, student_user, student_b_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )

    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=student_b_headers,
    )

    assert response.status_code == 404
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
    assert db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).count() == 0


def test_reopen_requires_authentication(client, db, student_user, seeded_departments):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    response = client.post(f"/api/v1/complaints/{complaint.id}/reopen", json={})
    assert response.status_code == 401


def test_reopen_is_forbidden_to_staff(
    client, db, student_user, staff_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=staff_headers,
    )
    assert response.status_code == 403


def test_reopen_nonexistent_complaint_returns_404(client, student_headers):
    response = client.post(
        "/api/v1/complaints/2147483647/reopen",
        json={},
        headers=student_headers,
    )
    assert response.status_code == 404


def test_reopen_rejects_complaint_that_is_not_resolved(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
        status="in_progress",
    )
    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=student_headers,
    )
    assert response.status_code == 409
    db.refresh(complaint)
    assert complaint.status == "in_progress"
    assert complaint.reopen_count == 0


def test_reopen_rejects_when_maximum_reopen_count_is_reached(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
        reopen_count=2,
    )
    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=student_headers,
    )
    assert response.status_code == 400
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 2


def test_reopen_rejects_after_seven_day_window(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
        resolved_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=student_headers,
    )
    assert response.status_code == 400
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0


def test_reopen_rejects_missing_resolution_timestamp(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
        resolved_at=None,
    )
    # The helper's default timestamp is overridden here to reproduce legacy/corrupt data.
    complaint.resolved_at = None
    db.commit()

    response = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={},
        headers=student_headers,
    )
    assert response.status_code == 400
    assert "resolution timestamp" in response.json()["detail"].lower()
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
    assert complaint.resolved_at is None


def test_reopen_rejects_invalid_id_and_extra_request_fields(
    client, db, student_user, student_headers, seeded_departments
):
    invalid_id = client.post("/api/v1/complaints/0/reopen", json={}, headers=student_headers)
    assert invalid_id.status_code == 422

    complaint = _resolved_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    extra_field = client.post(
        f"/api/v1/complaints/{complaint.id}/reopen",
        json={"remark": "Not allowed to inject fields.", "status": "resolved"},
        headers=student_headers,
    )
    assert extra_field.status_code == 422
    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
