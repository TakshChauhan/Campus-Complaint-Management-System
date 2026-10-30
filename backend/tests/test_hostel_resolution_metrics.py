"""S3-14: rolling resolution metrics grouped by hostel for the admin metrics page.

Covers:
1. Grouping by the hostel of the complaint's canonical floor_id
2. Active hostels with no resolved complaints still get a row
3. Inactive hostels appear only when they have resolved complaints in the window
4. Legacy text locations are never matched to a hostel; unlocated Hostel complaints are counted separately
5. Window, unresolved and negative-duration rules match calculate_rolling_resolution_metrics
6. department_id filter and invalid window
7. End to end: a complaint filed and resolved through the API is counted for its hostel
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.user import User
from app.services.complaint_lifecycle_service import (
    calculate_hostel_resolution_metrics,
    calculate_rolling_resolution_metrics,
)
from sprint3_hmc_world import headers_for, make_user

EMPTY_STATS = {
    "resolved_count": 0,
    "average_resolution_hours": None,
    "average_resolution_days": None,
    "median_resolution_hours": None,
    "min_resolution_hours": None,
    "max_resolution_hours": None,
}


def _hostel(db: Session, code: str, name: str, *, is_active: bool = True) -> HostelFloor:
    """Create a hostel with one wing and one floor; return the floor."""
    hostel = Hostel(code=code, name=name, is_active=is_active)
    db.add(hostel)
    db.flush()
    wing = HostelWing(hostel_id=hostel.id, code=code, name=f"Wing {code}")
    db.add(wing)
    db.flush()
    floor = HostelFloor(wing_id=wing.id, code="1", name="Floor 1")
    db.add(floor)
    db.commit()
    db.refresh(floor)
    return floor


def _resolved(
    db: Session,
    *,
    student: User,
    department_id: int,
    hours: float,
    resolved_days_ago: float = 1,
    floor: HostelFloor | None = None,
    hostel_text: str | None = None,
    status: str = "resolved",
) -> Complaint:
    resolved_at = datetime.now(timezone.utc) - timedelta(days=resolved_days_ago)
    complaint = Complaint(
        title="Hostel issue",
        description="Detailed description for testing hostel resolution metrics.",
        department_id=department_id,
        created_by_id=student.id,
        status=status,
        is_public=False,
        publication_status="private",
        floor_id=floor.id if floor else None,
        hostel=hostel_text,
        created_at=resolved_at - timedelta(hours=hours),
        resolved_at=resolved_at if status == "resolved" else None,
    )
    db.add(complaint)
    db.commit()
    return complaint


def _row(metrics: dict, hostel_code: str) -> dict:
    return next(row for row in metrics["hostels"] if row["hostel_code"] == hostel_code)


def test_groups_resolution_times_by_the_hostel_of_the_complaint_floor(
    db: Session, student_user: User, seeded_departments
):
    hostel_id = seeded_departments["hostel"].id
    north = _hostel(db, "NB", "North Block")
    south = _hostel(db, "SB", "South Block")
    _hostel(db, "EB", "East Block")

    _resolved(db, student=student_user, department_id=hostel_id, hours=10, floor=north)
    _resolved(db, student=student_user, department_id=hostel_id, hours=20, floor=north)
    _resolved(db, student=student_user, department_id=hostel_id, hours=30, floor=north)
    _resolved(db, student=student_user, department_id=hostel_id, hours=6, floor=south)

    metrics = calculate_hostel_resolution_metrics(db, window_days=30)

    assert metrics["window_days"] == 30
    assert metrics["department_id"] is None
    # Ordered by name; the active hostel without resolved complaints still has a row.
    assert [row["hostel_name"] for row in metrics["hostels"]] == ["East Block", "North Block", "South Block"]
    assert _row(metrics, "NB") == {
        "hostel_id": north.wing.hostel_id,
        "hostel_code": "NB",
        "hostel_name": "North Block",
        "is_active": True,
        "resolved_count": 3,
        "average_resolution_hours": 20.0,
        "average_resolution_days": 0.83,
        "median_resolution_hours": 20.0,
        "min_resolution_hours": 10.0,
        "max_resolution_hours": 30.0,
    }
    assert _row(metrics, "SB")["resolved_count"] == 1
    assert _row(metrics, "SB")["average_resolution_hours"] == 6.0
    assert {k: v for k, v in _row(metrics, "EB").items() if k in EMPTY_STATS} == EMPTY_STATS
    assert metrics["unlocated"] == EMPTY_STATS


def test_location_counts_where_the_issue_occurred_for_any_department(
    db: Session, student_user: User, seeded_departments
):
    north = _hostel(db, "NB", "North Block")
    _resolved(db, student=student_user, department_id=seeded_departments["it"].id, hours=4, floor=north)

    assert _row(calculate_hostel_resolution_metrics(db), "NB")["resolved_count"] == 1


def test_inactive_hostels_appear_only_with_resolved_complaints_in_the_window(
    db: Session, student_user: User, seeded_departments
):
    hostel_id = seeded_departments["hostel"].id
    closed = _hostel(db, "CB", "Closed Block", is_active=False)
    _hostel(db, "XB", "Empty Closed Block", is_active=False)
    _resolved(db, student=student_user, department_id=hostel_id, hours=8, floor=closed)

    metrics = calculate_hostel_resolution_metrics(db)

    assert [row["hostel_code"] for row in metrics["hostels"]] == ["CB"]
    assert _row(metrics, "CB")["is_active"] is False
    assert _row(metrics, "CB")["resolved_count"] == 1


def test_legacy_text_is_never_matched_and_unlocated_hostel_complaints_are_counted_separately(
    db: Session, student_user: User, seeded_departments
):
    _hostel(db, "NB", "North Block")
    hostel_id = seeded_departments["hostel"].id
    # Legacy text naming a real hostel, but no floor_id.
    _resolved(db, student=student_user, department_id=hostel_id, hours=12, hostel_text="North Block")
    _resolved(db, student=student_user, department_id=hostel_id, hours=36)
    # Unlocated complaints for other departments are not hostel matters.
    _resolved(db, student=student_user, department_id=seeded_departments["it"].id, hours=2)

    metrics = calculate_hostel_resolution_metrics(db)

    assert _row(metrics, "NB")["resolved_count"] == 0
    assert metrics["unlocated"]["resolved_count"] == 2
    assert metrics["unlocated"]["average_resolution_hours"] == 24.0


def test_window_unresolved_and_negative_durations_follow_the_rolling_rules(
    db: Session, student_user: User, seeded_departments
):
    hostel_id = seeded_departments["hostel"].id
    north = _hostel(db, "NB", "North Block")
    _resolved(db, student=student_user, department_id=hostel_id, hours=10, floor=north)
    _resolved(db, student=student_user, department_id=hostel_id, hours=50, floor=north, resolved_days_ago=35)
    _resolved(db, student=student_user, department_id=hostel_id, hours=5, floor=north, status="in_progress")
    _resolved(db, student=student_user, department_id=hostel_id, hours=-3, floor=north)

    assert _row(calculate_hostel_resolution_metrics(db, window_days=30), "NB")["resolved_count"] == 1
    wide = _row(calculate_hostel_resolution_metrics(db, window_days=60), "NB")
    assert wide["resolved_count"] == 2
    assert wide["average_resolution_hours"] == 30.0


def test_hostel_rows_and_unlocated_add_up_to_the_department_rolling_metric(
    db: Session, student_user: User, seeded_departments
):
    hostel_id = seeded_departments["hostel"].id
    north = _hostel(db, "NB", "North Block")
    south = _hostel(db, "SB", "South Block")
    for hours, floor in ((3, north), (9, north), (15, south), (21, None)):
        _resolved(db, student=student_user, department_id=hostel_id, hours=hours, floor=floor)
    _resolved(db, student=student_user, department_id=seeded_departments["it"].id, hours=1, floor=north)

    by_hostel = calculate_hostel_resolution_metrics(db, department_id=hostel_id)
    overall = calculate_rolling_resolution_metrics(db, department_id=hostel_id)

    assert by_hostel["department_id"] == hostel_id
    assert _row(by_hostel, "NB")["resolved_count"] == 2
    located = sum(row["resolved_count"] for row in by_hostel["hostels"])
    assert located + by_hostel["unlocated"]["resolved_count"] == overall["resolved_count"] == 4


def test_department_filter_for_another_department_excludes_hostel_complaints(
    db: Session, student_user: User, seeded_departments
):
    north = _hostel(db, "NB", "North Block")
    _resolved(db, student=student_user, department_id=seeded_departments["hostel"].id, hours=10, floor=north)
    _resolved(db, student=student_user, department_id=seeded_departments["hostel"].id, hours=10)

    metrics = calculate_hostel_resolution_metrics(db, department_id=seeded_departments["library"].id)

    assert _row(metrics, "NB")["resolved_count"] == 0
    assert metrics["unlocated"]["resolved_count"] == 0


@pytest.mark.parametrize("window_days", [0, -5])
def test_invalid_window_raises_400(db: Session, window_days: int):
    with pytest.raises(HTTPException) as exc_info:
        calculate_hostel_resolution_metrics(db, window_days=window_days)
    assert exc_info.value.status_code == 400
    assert "positive integer" in exc_info.value.detail


def test_complaint_filed_and_resolved_through_the_api_is_counted_for_its_hostel(
    client, db: Session, student_user: User, student_headers: dict, seeded_departments
):
    north = _hostel(db, "NB", "North Block")
    hostel_staff = make_user(db, "hostel.metrics", "staff", seeded_departments["hostel"].id)
    staff_headers = headers_for(hostel_staff)

    created = client.post("/api/v1/complaints", headers=student_headers, json={
        "title": "Leaking tap on floor 1",
        "description": "The washroom tap on floor 1 has been leaking for two days.",
        "department_id": seeded_departments["hostel"].id,
        "is_public": False,
        "floor_id": north.id,
    })
    assert created.status_code == 201, created.text
    complaint_id = created.json()["id"]

    assert _row(calculate_hostel_resolution_metrics(db), "NB")["resolved_count"] == 0

    for target in ("in_progress", "resolved"):
        response = client.patch(
            f"/api/v1/staff/complaints/{complaint_id}/status",
            headers=staff_headers,
            json={"status": target, "remark": f"Moved to {target}."},
        )
        assert response.status_code == 200, response.text

    row = _row(calculate_hostel_resolution_metrics(db), "NB")
    assert row["resolved_count"] == 1
    assert row["min_resolution_hours"] is not None and row["min_resolution_hours"] >= 0
