"""Tests for the read-only complaint status-history endpoint."""

from datetime import datetime, timedelta, timezone

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory


def _make_complaint(db, *, owner_id: int, department_id: int, is_public: bool = False) -> Complaint:
    complaint = Complaint(
        title="Broken campus Wi-Fi",
        description="The connection has been unavailable in the common room since this morning.",
        department_id=department_id,
        created_by_id=owner_id,
        status="in_progress",
        is_public=is_public,
        visibility_scope=("department_public" if is_public else "private"),
        feed_review_status="not_required",
        publication_status=("published" if is_public else "private"),
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def _add_event(
    db,
    *,
    complaint_id: int,
    actor_id: int,
    from_status: str | None,
    to_status: str,
    created_at: datetime,
    remark: str | None = None,
) -> ComplaintStatusHistory:
    event = ComplaintStatusHistory(
        complaint_id=complaint_id,
        actor_id=actor_id,
        from_status=from_status,
        to_status=to_status,
        created_at=created_at,
        remark=remark,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_student_can_read_own_history_in_chronological_order(
    client, db, student_user, student_headers, seeded_departments, staff_user
):
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    base = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)

    # Insert a later event first to verify ordering uses the event timestamp.
    _add_event(
        db,
        complaint_id=complaint.id,
        actor_id=staff_user.id,
        from_status="submitted",
        to_status="in_progress",
        created_at=base + timedelta(hours=2),
        remark="Investigation started.",
    )
    _add_event(
        db,
        complaint_id=complaint.id,
        actor_id=student_user.id,
        from_status=None,
        to_status="submitted",
        created_at=base,
        remark=None,
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=student_headers,
    )

    assert response.status_code == 200
    events = response.json()
    assert [event["to_status"] for event in events] == ["submitted", "in_progress"]
    assert events[0]["from_status"] is None
    assert events[1]["remark"] == "Investigation started."
    assert events[0]["actor_id"] == student_user.id
    assert "email" not in events[0]
    assert "name" not in events[0]
    assert "password_hash" not in events[0]


def test_history_returns_empty_array_when_no_events_exist(
    client, db, student_user, student_headers, seeded_departments
):
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=student_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_student_cannot_read_another_students_private_history(
    client, db, student_headers, student_b_user, seeded_departments
):
    complaint = _make_complaint(
        db,
        owner_id=student_b_user.id,
        department_id=seeded_departments["it"].id,
        is_public=False,
    )
    _add_event(
        db,
        complaint_id=complaint.id,
        actor_id=student_b_user.id,
        from_status=None,
        to_status="submitted",
        created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=student_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Complaint not found."


def test_student_cannot_read_another_students_public_history(
    client, db, student_headers, student_b_user, seeded_departments
):
    complaint = _make_complaint(
        db,
        owner_id=student_b_user.id,
        department_id=seeded_departments["it"].id,
        is_public=True,
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=student_headers,
    )

    assert response.status_code == 404


def test_staff_can_read_history_for_own_department(
    client, db, staff_user, staff_headers, student_user, seeded_departments
):
    staff_user.department_id = seeded_departments["it"].id
    db.commit()
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    _add_event(
        db,
        complaint_id=complaint.id,
        actor_id=student_user.id,
        from_status=None,
        to_status="submitted",
        created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=staff_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_staff_cannot_read_history_for_another_department(
    client, db, staff_user, staff_headers, student_user, seeded_departments
):
    staff_user.department_id = seeded_departments["it"].id
    db.commit()
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["hostel"].id,
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=staff_headers,
    )

    assert response.status_code == 404


def test_staff_without_department_cannot_read_history(
    client, db, staff_headers, student_user, seeded_departments
):
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=staff_headers,
    )

    assert response.status_code == 404


def test_admin_can_read_history_for_existing_complaint(
    client, db, admin_headers, student_user, seeded_departments
):
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    _add_event(
        db,
        complaint_id=complaint.id,
        actor_id=student_user.id,
        from_status=None,
        to_status="submitted",
        created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )

    response = client.get(
        f"/api/v1/complaints/{complaint.id}/history",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_missing_complaint_returns_404(client, student_headers):
    response = client.get(
        "/api/v1/complaints/2147483647/history",
        headers=student_headers,
    )
    assert response.status_code == 404


def test_history_requires_authentication(client, db, student_user, seeded_departments):
    complaint = _make_complaint(
        db,
        owner_id=student_user.id,
        department_id=seeded_departments["it"].id,
    )
    response = client.get(f"/api/v1/complaints/{complaint.id}/history")
    assert response.status_code == 401


def test_history_validates_positive_complaint_id(client, student_headers):
    response = client.get("/api/v1/complaints/0/history", headers=student_headers)
    assert response.status_code == 422
