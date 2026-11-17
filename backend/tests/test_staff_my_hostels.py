"""Route tests for GET /api/v1/staff/me/hostels (S4-14 staff dashboard support).

Covers roles (401/403), Hostel staff with one, two and no hostels, inactive
hostels being hidden, non-Hostel staff, staff without a department and staff of
an inactive department.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User

URL = "/api/v1/staff/me/hostels"


def _headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id), claims={"role": user.role, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _staff(db: Session, email: str, department_id: int | None) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash=get_password_hash("Password123!"),
        role="staff",
        is_active=True,
        department_id=department_id,
    )
    db.add(user)
    db.flush()
    return user


def _assign(db: Session, user: User, *hostels: Hostel) -> None:
    assigner = db.query(User).filter(User.role == "admin").first()
    db.add_all(
        [StaffHostelAssignment(user_id=user.id, hostel_id=h.id, assigned_by_id=assigner.id) for h in hostels]
    )
    db.flush()


@pytest.fixture
def hostels(db: Session, admin_user: User) -> dict:
    # admin_user is the assigning administrator recorded on every assignment.
    # Names chosen so that name order differs from insertion (id) order.
    items = {
        "zeta": Hostel(code="HZ", name="Zeta Hostel", is_active=True),
        "alpha": Hostel(code="HA", name="Alpha Hostel", is_active=True),
        "beta": Hostel(code="HB", name="Beta Hostel", is_active=True),
        "closed": Hostel(code="HX", name="Closed Hostel", is_active=False),
    }
    db.add_all(items.values())
    db.flush()
    return items


def test_requires_authentication(client: TestClient):
    assert client.get(URL).status_code == 401


def test_students_and_admins_are_forbidden(client: TestClient, student_headers: dict, admin_headers: dict):
    assert client.get(URL, headers=student_headers).status_code == 403
    assert client.get(URL, headers=admin_headers).status_code == 403


def test_staff_without_department_is_forbidden(client: TestClient, staff_headers: dict):
    response = client.get(URL, headers=staff_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Staff account is not assigned to a department."


def test_staff_of_inactive_department_is_forbidden(client: TestClient, db: Session, seeded_departments: dict):
    staff = _staff(db, "archived@campus.edu", seeded_departments["inactive"].id)
    db.commit()
    assert client.get(URL, headers=_headers(staff)).status_code == 403


def test_hostel_staff_with_one_hostel(client: TestClient, db: Session, seeded_departments: dict, hostels: dict):
    staff = _staff(db, "one@campus.edu", seeded_departments["hostel"].id)
    _assign(db, staff, hostels["beta"])
    db.commit()

    response = client.get(URL, headers=_headers(staff))

    assert response.status_code == 200
    assert response.json() == {
        "department_id": seeded_departments["hostel"].id,
        "hostel_scoped": True,
        "hostels": [{"id": hostels["beta"].id, "code": "HB", "name": "Beta Hostel"}],
    }


def test_hostel_staff_with_two_hostels_sorted_by_name(
    client: TestClient, db: Session, seeded_departments: dict, hostels: dict
):
    staff = _staff(db, "two@campus.edu", seeded_departments["hostel"].id)
    _assign(db, staff, hostels["zeta"], hostels["alpha"])
    db.commit()

    body = client.get(URL, headers=_headers(staff)).json()

    assert body["hostel_scoped"] is True
    assert [h["name"] for h in body["hostels"]] == ["Alpha Hostel", "Zeta Hostel"]
    # Only the caller's own hostels: Beta is not assigned to them.
    assert hostels["beta"].id not in {h["id"] for h in body["hostels"]}


def test_hostel_staff_with_no_hostels(client: TestClient, db: Session, seeded_departments: dict, hostels: dict):
    staff = _staff(db, "none@campus.edu", seeded_departments["hostel"].id)
    other = _staff(db, "other@campus.edu", seeded_departments["hostel"].id)
    _assign(db, other, hostels["alpha"])
    db.commit()

    body = client.get(URL, headers=_headers(staff)).json()

    assert body == {"department_id": seeded_departments["hostel"].id, "hostel_scoped": True, "hostels": []}


def test_inactive_assigned_hostel_is_hidden(client: TestClient, db: Session, seeded_departments: dict, hostels: dict):
    staff = _staff(db, "closed@campus.edu", seeded_departments["hostel"].id)
    _assign(db, staff, hostels["closed"], hostels["alpha"])
    db.commit()

    body = client.get(URL, headers=_headers(staff)).json()

    assert [h["code"] for h in body["hostels"]] == ["HA"]


def test_only_inactive_hostels_counts_as_none(
    client: TestClient, db: Session, seeded_departments: dict, hostels: dict
):
    staff = _staff(db, "onlyclosed@campus.edu", seeded_departments["hostel"].id)
    _assign(db, staff, hostels["closed"])
    db.commit()

    body = client.get(URL, headers=_headers(staff)).json()

    assert body["hostel_scoped"] is True
    assert body["hostels"] == []


def test_non_hostel_staff_are_not_hostel_scoped(
    client: TestClient, db: Session, seeded_departments: dict, hostels: dict
):
    staff = _staff(db, "it@campus.edu", seeded_departments["it"].id)
    # Even a stray assignment row must not make a non-Hostel staff member hostel-scoped.
    _assign(db, staff, hostels["alpha"])
    db.commit()

    body = client.get(URL, headers=_headers(staff)).json()

    assert body == {"department_id": seeded_departments["it"].id, "hostel_scoped": False, "hostels": []}
