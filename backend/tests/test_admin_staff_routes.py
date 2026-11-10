
"""Tests for administrator staff hostel assignment routes."""

import pytest

from app.models.department import Department
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User


API_PREFIX = "/api/v1/admin/staff"


def _create_staff(db, *, email="staff.routes@example.edu", department_id=None):
    staff = User(
        name="Test Staff",
        email=email,
        role="staff",
        is_active=True,
        department_id=department_id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def _create_hostel(db, *, code, name):
    hostel = Hostel(
        code=code,
        name=name,
        is_active=True,
    )
    db.add(hostel)
    db.commit()
    db.refresh(hostel)
    return hostel


def _assign_hostels(db, *, staff_id, hostel_ids, admin_id):
    for hostel_id in hostel_ids:
        db.add(
            StaffHostelAssignment(
                user_id=staff_id,
                hostel_id=hostel_id,
                assigned_by_id=admin_id,
            )
        )
    db.commit()


def _get_assignments(db, staff_id):
    return (
        db.query(StaffHostelAssignment)
        .filter(StaffHostelAssignment.user_id == staff_id)
        .all()
    )


# ---------------------------------------------------------
# GET /admin/staff
# ---------------------------------------------------------


def test_list_staff_requires_authentication(client):
    response = client.get(API_PREFIX)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "headers_fixture",
    ["student_headers", "staff_headers"],
)
def test_list_staff_is_admin_only(client, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)

    response = client.get(API_PREFIX, headers=headers)

    assert response.status_code == 403


def test_list_staff_returns_department_and_hostel_assignments(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    department = seeded_departments["hostel"]

    staff = _create_staff(
        db,
        department_id=department.id,
    )

    hostel_a = _create_hostel(
        db,
        code="ADMIN_A",
        name="Admin Hostel A",
    )
    hostel_b = _create_hostel(
        db,
        code="ADMIN_B",
        name="Admin Hostel B",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[hostel_a.id, hostel_b.id],
        admin_id=admin_user.id,
    )

    response = client.get(API_PREFIX, headers=admin_headers)

    assert response.status_code == 200

    staff_result = next(
        item for item in response.json()
        if item["id"] == staff.id
    )

    assert staff_result["name"] == "Test Staff"
    assert staff_result["email"] == "staff.routes@example.edu"
    assert staff_result["department_id"] == department.id
    assert staff_result["department_name"] == department.name

    assert {
        hostel["id"] for hostel in staff_result["hostels"]
    } == {hostel_a.id, hostel_b.id}


def test_list_staff_returns_empty_hostels_when_unassigned(
    client,
    db,
    admin_headers,
):
    staff = _create_staff(db)

    response = client.get(API_PREFIX, headers=admin_headers)

    assert response.status_code == 200

    staff_result = next(
        item for item in response.json()
        if item["id"] == staff.id
    )

    assert staff_result["hostels"] == []


# ---------------------------------------------------------
# PUT /admin/staff/{staff_id}/hostels
# ---------------------------------------------------------


def test_replace_assignments_requires_authentication(client, db):
    staff = _create_staff(db)

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": []},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "headers_fixture",
    ["student_headers", "staff_headers"],
)
def test_replace_assignments_is_admin_only(
    client,
    db,
    request,
    headers_fixture,
):
    staff = _create_staff(db)
    headers = request.getfixturevalue(headers_fixture)

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": []},
        headers=headers,
    )

    assert response.status_code == 403


def test_assign_multiple_hostels(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    hostel_a = _create_hostel(
        db,
        code="PUT_A",
        name="Put Hostel A",
    )
    hostel_b = _create_hostel(
        db,
        code="PUT_B",
        name="Put Hostel B",
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [hostel_a.id, hostel_b.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == staff.id
    assert {
        hostel["id"] for hostel in payload["hostels"]
    } == {hostel_a.id, hostel_b.id}

    assignments = _get_assignments(db, staff.id)

    assert len(assignments) == 2
    assert all(
        assignment.assigned_by_id == admin_user.id
        for assignment in assignments
    )


def test_replace_assignments_removes_old_hostels(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    old_hostel = _create_hostel(
        db,
        code="OLD_A",
        name="Old Hostel",
    )
    new_hostel = _create_hostel(
        db,
        code="NEW_A",
        name="New Hostel",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[old_hostel.id],
        admin_id=admin_user.id,
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [new_hostel.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200

    assert [
        hostel["id"] for hostel in response.json()["hostels"]
    ] == [new_hostel.id]

    assignments = _get_assignments(db, staff.id)

    assert len(assignments) == 1
    assert assignments[0].hostel_id == new_hostel.id


def test_empty_hostel_list_clears_all_assignments(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    hostel = _create_hostel(
        db,
        code="CLEAR_A",
        name="Clear Hostel",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[hostel.id],
        admin_id=admin_user.id,
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": []},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["hostels"] == []

    assert _get_assignments(db, staff.id) == []


@pytest.mark.parametrize("invalid_role", ["student", "admin"])
def test_assignment_rejects_non_staff_users(
    client,
    db,
    admin_headers,
    invalid_role,
):
    user = User(
        name="Not Staff",
        email=f"notstaff.{invalid_role}@example.edu",
        role=invalid_role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.put(
        f"{API_PREFIX}/{user.id}/hostels",
        json={"hostel_ids": []},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_assignment_rejects_unknown_staff_id(
    client,
    admin_headers,
):
    response = client.put(
        f"{API_PREFIX}/999999/hostels",
        json={"hostel_ids": []},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_assignment_rejects_unknown_hostel_without_deleting_existing(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    existing_hostel = _create_hostel(
        db,
        code="KEEP_A",
        name="Keep Existing Hostel",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[existing_hostel.id],
        admin_id=admin_user.id,
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [999999]},
        headers=admin_headers,
    )

    assert response.status_code == 422

    remaining = _get_assignments(db, staff.id)

    assert len(remaining) == 1
    assert remaining[0].hostel_id == existing_hostel.id


def test_assignment_deduplicates_hostel_ids(
    client,
    db,
    admin_headers,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    hostel = _create_hostel(
        db,
        code="DUP_A",
        name="Duplicate Test Hostel",
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [hostel.id, hostel.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["hostels"]) == 1


# ---------------------------------------------------------
# NEW VALIDATION TESTS REQUESTED IN PR REVIEW
# ---------------------------------------------------------


def test_assignment_rejects_non_hostel_staff_without_deleting_existing(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    # Use the seeded non-Hostel department.
    other_department = seeded_departments["library"]

    staff = _create_staff(
        db,
        email="other.department.staff@example.edu",
        department_id=other_department.id,
    )

    existing_hostel = _create_hostel(
        db,
        code="IT_KEEP",
        name="Existing Assigned Hostel",
    )

    requested_hostel = _create_hostel(
        db,
        code="IT_NEW",
        name="Requested Hostel",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[existing_hostel.id],
        admin_id=admin_user.id,
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [requested_hostel.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422

    remaining = _get_assignments(db, staff.id)

    assert len(remaining) == 1
    assert remaining[0].hostel_id == existing_hostel.id




def test_assignment_rejects_inactive_hostel_without_deleting_existing(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    staff = _create_staff(
        db,
        department_id=seeded_departments["hostel"].id,
    )

    existing_hostel = _create_hostel(
        db,
        code="ACTIVE_KEEP",
        name="Existing Active Hostel",
    )

    inactive_hostel = _create_hostel(
        db,
        code="INACTIVE_NEW",
        name="Inactive Hostel",
    )

    inactive_hostel.is_active = False
    db.commit()

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[existing_hostel.id],
        admin_id=admin_user.id,
    )

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": [inactive_hostel.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422

    remaining = _get_assignments(db, staff.id)

    assert len(remaining) == 1
    assert remaining[0].hostel_id == existing_hostel.id


def test_assignment_rejects_inactive_hostel_department_without_deleting_existing(
    client,
    db,
    admin_headers,
    admin_user,
    seeded_departments,
):
    department = seeded_departments["hostel"]

    staff = _create_staff(
        db,
        department_id=department.id,
    )

    existing_hostel = _create_hostel(
        db,
        code="DEPT_KEEP",
        name="Existing Department Hostel",
    )

    _assign_hostels(
        db,
        staff_id=staff.id,
        hostel_ids=[existing_hostel.id],
        admin_id=admin_user.id,
    )

    department.is_active = False
    db.commit()

    response = client.put(
        f"{API_PREFIX}/{staff.id}/hostels",
        json={"hostel_ids": []},
        headers=admin_headers,
    )

    assert response.status_code == 422

    remaining = _get_assignments(db, staff.id)

    assert len(remaining) == 1
    assert remaining[0].hostel_id == existing_hostel.id
