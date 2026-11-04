"""Integration tests for administrator complaint metrics endpoints."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing


API_PREFIX = "/api/v1/admin/metrics"


def _add_complaint(db, *, department_id, created_by_id, status, hours_ago=48, resolved_hours_ago=None):
    now = datetime.now(timezone.utc)
    complaint = Complaint(
        title=f"Test complaint {status}",
        description="A test complaint used for admin metrics route coverage.",
        department_id=department_id,
        created_by_id=created_by_id,
        status=status,
        created_at=now - timedelta(hours=hours_ago),
        updated_at=now,
        resolved_at=(now - timedelta(hours=resolved_hours_ago)) if resolved_hours_ago is not None else None,
    )
    db.add(complaint)
    db.flush()
    return complaint


def test_resolution_metrics_requires_authentication(client):
    response = client.get(f"{API_PREFIX}/resolution")
    assert response.status_code == 401


@pytest.mark.parametrize("headers_fixture", ["student_headers", "staff_headers"] )
def test_resolution_metrics_is_admin_only(client, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    response = client.get(f"{API_PREFIX}/resolution", headers=headers)
    assert response.status_code == 403


def test_resolution_metrics_returns_existing_lifecycle_calculation(client, db, seeded_departments, student_user, admin_headers):
    it = seeded_departments["it"]
    _add_complaint(
        db,
        department_id=it.id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=30,
        resolved_hours_ago=6,
    )
    db.commit()

    response = client.get(f"{API_PREFIX}/resolution?window_days=30&department_id={it.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "window_days": 30,
        "department_id": it.id,
        "resolved_count": 1,
        "average_resolution_hours": 24.0,
        "average_resolution_days": 1.0,
        "median_resolution_hours": 24.0,
        "min_resolution_hours": 24.0,
        "max_resolution_hours": 24.0,
    }


def test_resolution_metrics_rejects_non_positive_window(client, admin_headers):
    response = client.get(f"{API_PREFIX}/resolution?window_days=0", headers=admin_headers)
    assert response.status_code == 422


def test_summary_requires_authentication(client):
    response = client.get(f"{API_PREFIX}/summary")
    assert response.status_code == 401


@pytest.mark.parametrize("headers_fixture", ["student_headers", "staff_headers"] )
def test_summary_is_admin_only(client, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    response = client.get(f"{API_PREFIX}/summary", headers=headers)
    assert response.status_code == 403


def test_summary_returns_all_statuses_active_departments_and_resolution_metrics(
    client, db, seeded_departments, student_user, admin_headers
):
    departments = seeded_departments
    _add_complaint(db, department_id=departments["it"].id, created_by_id=student_user.id, status="submitted")
    _add_complaint(db, department_id=departments["it"].id, created_by_id=student_user.id, status="in_progress")
    _add_complaint(
        db,
        department_id=departments["hostel"].id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=30,
        resolved_hours_ago=6,
    )
    _add_complaint(db, department_id=departments["inactive"].id, created_by_id=student_user.id, status="reopened")
    db.commit()

    response = client.get(f"{API_PREFIX}/summary", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_complaints"] == 4
    assert payload["status_counts"] == [
        {"status": "submitted", "count": 1},
        {"status": "in_progress", "count": 1},
        {"status": "resolved", "count": 1},
        {"status": "reopened", "count": 1},
    ]
    assert payload["department_counts"] == [
        {"department_id": departments["hostel"].id, "department_name": "Hostel", "count": 1},
        {"department_id": departments["it"].id, "department_name": "IT Services", "count": 2},
        {"department_id": departments["library"].id, "department_name": "Library", "count": 0},
    ]
    assert payload["resolution_metrics"] == {
        "window_days": 30,
        "department_id": None,
        "resolved_count": 1,
        "average_resolution_hours": 24.0,
        "average_resolution_days": 1.0,
        "median_resolution_hours": 24.0,
        "min_resolution_hours": 24.0,
        "max_resolution_hours": 24.0,
    }


def test_summary_returns_zero_counts_for_empty_database(client, db, seeded_departments, admin_headers):
    response = client.get(f"{API_PREFIX}/summary", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_complaints"] == 0
    assert payload["status_counts"] == [
        {"status": "submitted", "count": 0},
        {"status": "in_progress", "count": 0},
        {"status": "resolved", "count": 0},
        {"status": "reopened", "count": 0},
    ]
    assert all(item["count"] == 0 for item in payload["department_counts"])
    assert payload["resolution_metrics"]["resolved_count"] == 0
    assert payload["resolution_metrics"]["average_resolution_hours"] is None


def _add_hostel_floor(db, *, code="METRICS_NB", name="Metrics North Block"):
    """Create a canonical hostel/wing/floor hierarchy for route tests."""
    hostel = Hostel(code=code, name=name, is_active=True)
    db.add(hostel)
    db.flush()

    wing = HostelWing(
        hostel_id=hostel.id,
        code=f"{code}_A",
        name="Wing A",
        is_active=True,
    )
    db.add(wing)
    db.flush()

    floor = HostelFloor(wing_id=wing.id, code="1", name="Floor 1", is_active=True)
    db.add(floor)
    db.flush()
    return hostel, floor


def test_hostel_resolution_metrics_requires_authentication(client):
    response = client.get(f"{API_PREFIX}/resolution/by-hostel")
    assert response.status_code == 401


@pytest.mark.parametrize("headers_fixture", ["student_headers", "staff_headers"])
def test_hostel_resolution_metrics_is_admin_only(client, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    response = client.get(f"{API_PREFIX}/resolution/by-hostel", headers=headers)
    assert response.status_code == 403


def test_hostel_resolution_metrics_returns_hostel_and_unlocated_statistics(
    client, db, seeded_departments, student_user, admin_headers
):
    departments = seeded_departments
    hostel, floor = _add_hostel_floor(db)

    located = _add_complaint(
        db,
        department_id=departments["hostel"].id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=30,
        resolved_hours_ago=6,
    )
    located.floor_id = floor.id

    _add_complaint(
        db,
        department_id=departments["hostel"].id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=48,
        resolved_hours_ago=12,
    )
    # An unlocated complaint for another department must not enter the
    # Hostel-department unlocated bucket.
    _add_complaint(
        db,
        department_id=departments["it"].id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=24,
        resolved_hours_ago=1,
    )
    db.commit()

    response = client.get(f"{API_PREFIX}/resolution/by-hostel", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_days"] == 30
    assert payload["department_id"] is None
    assert payload["hostels"] == [
        {
            "hostel_id": hostel.id,
            "hostel_code": "METRICS_NB",
            "hostel_name": "Metrics North Block",
            "is_active": True,
            "resolved_count": 1,
            "average_resolution_hours": 24.0,
            "average_resolution_days": 1.0,
            "median_resolution_hours": 24.0,
            "min_resolution_hours": 24.0,
            "max_resolution_hours": 24.0,
        }
    ]
    assert payload["unlocated"] == {
        "resolved_count": 1,
        "average_resolution_hours": 36.0,
        "average_resolution_days": 1.5,
        "median_resolution_hours": 36.0,
        "min_resolution_hours": 36.0,
        "max_resolution_hours": 36.0,
    }


@pytest.mark.parametrize("query", ["window_days=0", "department_id=0"])
def test_hostel_resolution_metrics_rejects_non_positive_query_values(client, admin_headers, query):
    response = client.get(f"{API_PREFIX}/resolution/by-hostel?{query}", headers=admin_headers)
    assert response.status_code == 422


def test_hostel_resolution_metrics_applies_department_filter(
    client, db, seeded_departments, student_user, admin_headers
):
    departments = seeded_departments
    hostel, floor = _add_hostel_floor(db)
    located = _add_complaint(
        db,
        department_id=departments["it"].id,
        created_by_id=student_user.id,
        status="resolved",
        hours_ago=30,
        resolved_hours_ago=6,
    )
    located.floor_id = floor.id
    db.commit()

    response = client.get(
        f"{API_PREFIX}/resolution/by-hostel?department_id={departments['it'].id}",
        headers=admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["department_id"] == departments["it"].id
    assert payload["hostels"][0]["resolved_count"] == 1
    assert payload["unlocated"]["resolved_count"] == 0
