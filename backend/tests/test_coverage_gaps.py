"""Unit and route tests for hostel coverage gaps endpoint (S4-07)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User


def _build_hostel_hierarchy(db: Session, code: str, name: str, is_active: bool = True) -> tuple[Hostel, HostelWing, HostelFloor]:
    hostel = Hostel(code=code, name=name, is_active=is_active)
    db.add(hostel)
    db.flush()

    wing = HostelWing(hostel_id=hostel.id, code=f"{code}-W", name=f"{name} Wing", is_active=is_active)
    db.add(wing)
    db.flush()

    floor = HostelFloor(wing_id=wing.id, code=f"{code}-W-F1", name=f"{name} Floor 1", is_active=is_active)
    db.add(floor)
    db.flush()

    return hostel, wing, floor


def _add_complaint(db: Session, *, floor_id: int, department_id: int, created_by_id: int, status: str = "submitted") -> Complaint:
    complaint = Complaint(
        title=f"Complaint in floor {floor_id}",
        description="Issue description for coverage gap testing",
        department_id=department_id,
        created_by_id=created_by_id,
        status=status,
        floor_id=floor_id,
        is_public=False,
    )
    db.add(complaint)
    db.flush()
    return complaint


def test_coverage_gaps_requires_admin_role(client: TestClient, student_headers: dict, staff_headers: dict):
    """Anonymous gets 401; student and staff get 403."""
    unauth_resp = client.get("/api/v1/admin/coverage-gaps")
    assert unauth_resp.status_code == 401

    student_resp = client.get("/api/v1/admin/coverage-gaps", headers=student_headers)
    assert student_resp.status_code == 403

    staff_resp = client.get("/api/v1/admin/coverage-gaps", headers=staff_headers)
    assert staff_resp.status_code == 403


def test_coverage_gaps_identifies_unstaffed_hostels_with_open_complaints(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    admin_user: User,
    student_user: User,
    staff_user: User,
    seeded_departments: dict,
):
    """Hostel with open complaints and no staff is listed.

    Hostel with staff is NOT listed.
    Hostel with only resolved complaints is NOT listed.
    Hostel with zero complaints is NOT listed.
    """
    dept_id = seeded_departments["hostel"].id

    # 1. Hostel A: unstaffed, 2 open complaints -> MUST be listed
    hostel_a, _, floor_a = _build_hostel_hierarchy(db, "HGA", "Hostel Alpha")
    _add_complaint(db, floor_id=floor_a.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")
    _add_complaint(db, floor_id=floor_a.id, department_id=dept_id, created_by_id=student_user.id, status="in_progress")

    # 2. Hostel B: staffed, 2 open complaints -> MUST NOT be listed
    hostel_b, _, floor_b = _build_hostel_hierarchy(db, "HGB", "Hostel Beta")
    _add_complaint(db, floor_id=floor_b.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")
    _add_complaint(db, floor_id=floor_b.id, department_id=dept_id, created_by_id=student_user.id, status="reopened")
    db.add(StaffHostelAssignment(user_id=staff_user.id, hostel_id=hostel_b.id, assigned_by_id=admin_user.id))

    # 3. Hostel C: unstaffed, only resolved complaints -> MUST NOT be listed
    hostel_c, _, floor_c = _build_hostel_hierarchy(db, "HGC", "Hostel Gamma")
    _add_complaint(db, floor_id=floor_c.id, department_id=dept_id, created_by_id=student_user.id, status="resolved")

    # 4. Hostel D: unstaffed, zero complaints -> MUST NOT be listed
    hostel_d, _, _ = _build_hostel_hierarchy(db, "HGD", "Hostel Delta")

    db.commit()

    resp = client.get("/api/v1/admin/coverage-gaps", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 1
    assert data[0]["hostel_id"] == hostel_a.id
    assert data[0]["hostel_name"] == "Hostel Alpha"
    assert data[0]["open_count"] == 2


def test_coverage_gaps_includes_all_open_statuses(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    student_user: User,
    seeded_departments: dict,
):
    """Counts submitted, in_progress, and reopened complaints, but excludes resolved."""
    dept_id = seeded_departments["hostel"].id
    hostel, _, floor = _build_hostel_hierarchy(db, "HGE", "Hostel Epsilon")

    _add_complaint(db, floor_id=floor.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")
    _add_complaint(db, floor_id=floor.id, department_id=dept_id, created_by_id=student_user.id, status="in_progress")
    _add_complaint(db, floor_id=floor.id, department_id=dept_id, created_by_id=student_user.id, status="reopened")
    _add_complaint(db, floor_id=floor.id, department_id=dept_id, created_by_id=student_user.id, status="resolved")
    db.commit()

    resp = client.get("/api/v1/admin/coverage-gaps", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    matched = [item for item in data if item["hostel_id"] == hostel.id]
    assert len(matched) == 1
    assert matched[0]["open_count"] == 3


def test_coverage_gaps_excludes_inactive_hostels(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    student_user: User,
    seeded_departments: dict,
):
    """An inactive hostel with open complaints must not appear in coverage gaps."""
    dept_id = seeded_departments["hostel"].id
    hostel, _, floor = _build_hostel_hierarchy(db, "HGZ", "Hostel Zeta (Inactive)", is_active=False)
    _add_complaint(db, floor_id=floor.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")
    db.commit()

    resp = client.get("/api/v1/admin/coverage-gaps", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert not any(item["hostel_id"] == hostel.id for item in data)


def test_coverage_gaps_ordered_by_open_count_desc(
    client: TestClient,
    db: Session,
    admin_headers: dict,
    student_user: User,
    seeded_departments: dict,
):
    """Hostels are sorted with highest open complaints first."""
    dept_id = seeded_departments["hostel"].id

    h1, _, f1 = _build_hostel_hierarchy(db, "HG1", "Hostel One")
    _add_complaint(db, floor_id=f1.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")

    h2, _, f2 = _build_hostel_hierarchy(db, "HG2", "Hostel Two")
    for _ in range(4):
        _add_complaint(db, floor_id=f2.id, department_id=dept_id, created_by_id=student_user.id, status="submitted")

    db.commit()

    resp = client.get("/api/v1/admin/coverage-gaps", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    matching = [item for item in data if item["hostel_id"] in (h1.id, h2.id)]
    assert len(matching) == 2
    assert matching[0]["hostel_id"] == h2.id
    assert matching[0]["open_count"] == 4
    assert matching[1]["hostel_id"] == h1.id
    assert matching[1]["open_count"] == 1
