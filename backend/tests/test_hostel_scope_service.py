"""Tests for the Hostel Scope Service (S4-06).

Verifies the 5 mandatory scoping scenarios:
1. Admin (unrestricted, covers all active hostels).
2. Hostel staff with 1 assigned hostel.
3. Hostel staff with multiple assigned hostels.
4. Hostel staff with 0 assigned hostels (fail-closed, returns 0 records).
5. Non-Hostel department staff (preserves existing department behaviour).
Along with inactive hostel handling and explicit model parameter passing.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.services.hostel_scope_service import (
    StaffScope,
    apply_scope,
    get_staff_scope,
)


@pytest.fixture
def hostel_world(db: Session, seeded_departments: dict):
    """Seed a realistic location tree, users, complaints, and residences."""
    hostel_dept = seeded_departments["hostel"]
    it_dept = seeded_departments["it"]

    # 1. Create Hostels (3 active, 1 inactive)
    hostel_a = Hostel(code="HA", name="Hostel A", is_active=True)
    hostel_b = Hostel(code="HB", name="Hostel B", is_active=True)
    hostel_c = Hostel(code="HC", name="Hostel C", is_active=True)
    hostel_inact = Hostel(code="HI", name="Hostel Inactive", is_active=False)
    db.add_all([hostel_a, hostel_b, hostel_c, hostel_inact])
    db.flush()

    # 2. Create Wings
    wing_a = HostelWing(hostel_id=hostel_a.id, code="WA", name="Wing A", is_active=True)
    wing_b = HostelWing(hostel_id=hostel_b.id, code="WB", name="Wing B", is_active=True)
    wing_c = HostelWing(hostel_id=hostel_c.id, code="WC", name="Wing C", is_active=True)
    wing_inact = HostelWing(hostel_id=hostel_inact.id, code="WI", name="Wing Inactive", is_active=True)
    db.add_all([wing_a, wing_b, wing_c, wing_inact])
    db.flush()

    # 3. Create Floors
    floor_a = HostelFloor(wing_id=wing_a.id, code="FA1", name="Floor A1", is_active=True)
    floor_b = HostelFloor(wing_id=wing_b.id, code="FB1", name="Floor B1", is_active=True)
    floor_c = HostelFloor(wing_id=wing_c.id, code="FC1", name="Floor C1", is_active=True)
    floor_inact = HostelFloor(wing_id=wing_inact.id, code="FI1", name="Floor Inactive", is_active=True)
    db.add_all([floor_a, floor_b, floor_c, floor_inact])
    db.flush()

    # 4. Create Students
    student_1 = User(name="Student 1", email="s1@student.campus.edu", role="student", is_active=True)
    student_2 = User(name="Student 2", email="s2@student.campus.edu", role="student", is_active=True)
    student_3 = User(name="Student 3", email="s3@student.campus.edu", role="student", is_active=True)
    db.add_all([student_1, student_2, student_3])
    db.flush()

    # 5. Create Staff and Admin users
    admin_user = User(name="Admin Boss", email="admin.scope@campus.edu", role="admin", is_active=True)
    staff_single = User(
        name="Staff Single",
        email="staff.single@campus.edu",
        role="staff",
        department_id=hostel_dept.id,
        is_active=True,
    )
    staff_multi = User(
        name="Staff Multi",
        email="staff.multi@campus.edu",
        role="staff",
        department_id=hostel_dept.id,
        is_active=True,
    )
    staff_unassigned = User(
        name="Staff Unassigned",
        email="staff.none@campus.edu",
        role="staff",
        department_id=hostel_dept.id,
        is_active=True,
    )
    staff_inactive = User(
        name="Staff Inactive Hostel",
        email="staff.inact@campus.edu",
        role="staff",
        department_id=hostel_dept.id,
        is_active=True,
    )
    it_staff = User(
        name="IT Staff",
        email="it.staff@campus.edu",
        role="staff",
        department_id=it_dept.id,
        is_active=True,
    )
    db.add_all([admin_user, staff_single, staff_multi, staff_unassigned, staff_inactive, it_staff])
    db.flush()

    # 6. Create Staff-Hostel Assignments
    assign_single_a = StaffHostelAssignment(
        user_id=staff_single.id,
        hostel_id=hostel_a.id,
        assigned_by_id=admin_user.id,
    )
    assign_multi_a = StaffHostelAssignment(
        user_id=staff_multi.id,
        hostel_id=hostel_a.id,
        assigned_by_id=admin_user.id,
    )
    assign_multi_b = StaffHostelAssignment(
        user_id=staff_multi.id,
        hostel_id=hostel_b.id,
        assigned_by_id=admin_user.id,
    )
    assign_inactive = StaffHostelAssignment(
        user_id=staff_inactive.id,
        hostel_id=hostel_inact.id,
        assigned_by_id=admin_user.id,
    )
    db.add_all([assign_single_a, assign_multi_a, assign_multi_b, assign_inactive])
    db.flush()

    # 7. Create Complaints across hostels and departments
    complaint_a = Complaint(
        title="Tap leaking in Hostel A",
        description="Bathroom faucet is leaking on Floor A1.",
        department_id=hostel_dept.id,
        created_by_id=student_1.id,
        floor_id=floor_a.id,
        status="submitted",
    )
    complaint_b = Complaint(
        title="Fan broken in Hostel B",
        description="Ceiling fan making noise on Floor B1.",
        department_id=hostel_dept.id,
        created_by_id=student_2.id,
        floor_id=floor_b.id,
        status="in_progress",
    )
    complaint_c = Complaint(
        title="Light bulb out in Hostel C",
        description="Corridor light not working on Floor C1.",
        department_id=hostel_dept.id,
        created_by_id=student_3.id,
        floor_id=floor_c.id,
        status="resolved",
    )
    complaint_it = Complaint(
        title="Wi-Fi slow in academic block",
        description="Campus Wi-Fi connectivity drop.",
        department_id=it_dept.id,
        created_by_id=student_1.id,
        floor_id=None,
        status="submitted",
    )
    db.add_all([complaint_a, complaint_b, complaint_c, complaint_it])
    db.flush()

    # 8. Create Student Residences across hostels
    residence_a = StudentResidence(
        student_id=student_1.id,
        floor_id=floor_a.id,
        status="verified",
    )
    residence_b = StudentResidence(
        student_id=student_2.id,
        floor_id=floor_b.id,
        status="pending",
    )
    residence_c = StudentResidence(
        student_id=student_3.id,
        floor_id=floor_c.id,
        status="rejected",
    )
    db.add_all([residence_a, residence_b, residence_c])
    db.commit()

    return {
        "hostels": {"a": hostel_a, "b": hostel_b, "c": hostel_c, "inactive": hostel_inact},
        "users": {
            "admin": admin_user,
            "staff_single": staff_single,
            "staff_multi": staff_multi,
            "staff_unassigned": staff_unassigned,
            "staff_inactive": staff_inactive,
            "it_staff": it_staff,
            "student_1": student_1,
        },
        "complaints": {
            "a": complaint_a,
            "b": complaint_b,
            "c": complaint_c,
            "it": complaint_it,
        },
        "residences": {
            "a": residence_a,
            "b": residence_b,
            "c": residence_c,
        },
        "it_dept": it_dept,
        "hostel_dept": hostel_dept,
    }


def test_admin_scope_covers_all_active_hostels_and_unrestricted_query(db: Session, hostel_world: dict):
    """Admin has universal scope and query is returned without hostel filtering."""
    admin = hostel_world["users"]["admin"]
    hostels = hostel_world["hostels"]

    scope = get_staff_scope(db, admin)

    assert scope.is_admin is True
    assert scope.is_hostel_staff is False
    assert hostels["a"].id in scope.hostel_ids
    assert hostels["b"].id in scope.hostel_ids
    assert hostels["c"].id in scope.hostel_ids
    # Inactive hostel should not be in active hostel_ids
    assert hostels["inactive"].id not in scope.hostel_ids

    # Query on complaints is unrestricted (sees all 4, including the non-hostel IT complaint)
    complaints_query = apply_scope(db.query(Complaint), scope)
    assert complaints_query.count() == 4

    # Query on student residences is unrestricted (sees all 3)
    residences_query = apply_scope(db.query(StudentResidence), scope)
    assert residences_query.count() == 3


def test_hostel_staff_single_hostel_assignment(db: Session, hostel_world: dict):
    """Hostel staff with 1 assigned hostel sees only complaints and residences for that hostel."""
    staff = hostel_world["users"]["staff_single"]
    hostel_a = hostel_world["hostels"]["a"]
    complaint_a = hostel_world["complaints"]["a"]
    residence_a = hostel_world["residences"]["a"]

    scope = get_staff_scope(db, staff)

    assert scope.is_admin is False
    assert scope.is_hostel_staff is True
    assert scope.hostel_ids == {hostel_a.id}

    # Complaints query returns only Complaint A
    complaints = apply_scope(db.query(Complaint), scope).all()
    assert [c.id for c in complaints] == [complaint_a.id]

    # Residences query returns only Residence A
    residences = apply_scope(db.query(StudentResidence), scope).all()
    assert [r.id for r in residences] == [residence_a.id]


def test_hostel_staff_multiple_hostel_assignments(db: Session, hostel_world: dict):
    """Hostel staff with multiple assigned hostels sees complaints and residences across all assigned hostels."""
    staff = hostel_world["users"]["staff_multi"]
    hostel_a = hostel_world["hostels"]["a"]
    hostel_b = hostel_world["hostels"]["b"]
    complaint_a = hostel_world["complaints"]["a"]
    complaint_b = hostel_world["complaints"]["b"]
    residence_a = hostel_world["residences"]["a"]
    residence_b = hostel_world["residences"]["b"]

    scope = get_staff_scope(db, staff)

    assert scope.is_admin is False
    assert scope.is_hostel_staff is True
    assert scope.hostel_ids == {hostel_a.id, hostel_b.id}

    # Complaints query returns Complaints A and B, but NOT C or IT
    complaints = apply_scope(db.query(Complaint), scope).all()
    assert {c.id for c in complaints} == {complaint_a.id, complaint_b.id}

    # Residences query returns Residences A and B, but NOT C
    residences = apply_scope(db.query(StudentResidence), scope).all()
    assert {r.id for r in residences} == {residence_a.id, residence_b.id}


def test_hostel_staff_zero_assignments_fails_closed(db: Session, hostel_world: dict):
    """Hostel staff with 0 assignments has empty scope and receives 0 records (fail-closed)."""
    staff = hostel_world["users"]["staff_unassigned"]

    scope = get_staff_scope(db, staff)

    assert scope.is_admin is False
    assert scope.is_hostel_staff is True
    assert scope.hostel_ids == set()

    # Query returns zero complaints
    complaint_query = apply_scope(db.query(Complaint), scope)
    assert complaint_query.count() == 0
    assert complaint_query.all() == []

    # Query returns zero residences
    residence_query = apply_scope(db.query(StudentResidence), scope)
    assert residence_query.count() == 0
    assert residence_query.all() == []


def test_non_hostel_staff_preserves_existing_behaviour(db: Session, hostel_world: dict):
    """Staff from non-Hostel departments are not subject to hostel assignment restrictions."""
    it_staff = hostel_world["users"]["it_staff"]
    it_dept = hostel_world["it_dept"]
    complaint_it = hostel_world["complaints"]["it"]

    scope = get_staff_scope(db, it_staff)

    assert scope.is_admin is False
    assert scope.is_hostel_staff is False
    assert scope.hostel_ids == set()
    assert scope.department_id == it_dept.id

    # Existing department query is not restricted by hostel assignments
    base_query = db.query(Complaint).filter(Complaint.department_id == it_dept.id)
    scoped_query = apply_scope(base_query, scope)

    results = scoped_query.all()
    assert [c.id for c in results] == [complaint_it.id]


def test_inactive_hostel_assignment_excluded_from_scope(db: Session, hostel_world: dict):
    """Assignments to deactivated hostels must not grant active scope."""
    staff = hostel_world["users"]["staff_inactive"]

    scope = get_staff_scope(db, staff)

    assert scope.is_hostel_staff is True
    # The assigned hostel is inactive, so scope.hostel_ids must be empty
    assert scope.hostel_ids == set()

    # Therefore, queries fail closed and return 0 records
    complaints = apply_scope(db.query(Complaint), scope).all()
    assert complaints == []


def test_none_user_returns_safe_empty_scope(db: Session):
    """Passing None as user returns safe unauthenticated scope."""
    scope = get_staff_scope(db, None)

    assert scope == StaffScope(
        is_admin=False,
        is_hostel_staff=False,
        hostel_ids=set(),
        department_id=None,
    )


def test_apply_scope_with_explicit_model_param(db: Session, hostel_world: dict):
    """apply_scope works when the model parameter is passed explicitly."""
    staff = hostel_world["users"]["staff_single"]
    complaint_a = hostel_world["complaints"]["a"]

    scope = get_staff_scope(db, staff)

    complaints = apply_scope(db.query(Complaint), scope, model=Complaint).all()
    assert [c.id for c in complaints] == [complaint_a.id]

