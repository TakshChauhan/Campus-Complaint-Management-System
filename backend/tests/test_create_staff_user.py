from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.scripts.create_staff_user import provision_user


def test_creates_verified_demo_student(db):
    user, created = provision_user(
        db,
        email="demo.student@dau.ac.in",
        name="Demo Student",
        role="student",
        password="SafePassword123!",
    )

    assert created is True
    assert user.role == "student"
    assert user.email_verified is True
    assert user.email_verification_required is False
    assert user.department_id is None


def test_creates_hostel_staff_with_assignments(db, seeded_departments):
    hostel = Hostel(code="A", name="Hostel A", is_active=True)
    db.add(hostel)
    db.commit()
    db.refresh(hostel)

    user, created = provision_user(
        db,
        email="hostel.staff@dau.ac.in",
        name="Hostel Staff",
        role="staff",
        department_name="Hostel",
        hostel_ids=[hostel.id],
        password="SafePassword123!",
    )

    assert created is True
    assert user.department.name == "Hostel"
    assignment = db.query(StaffHostelAssignment).one()
    assert assignment.user_id == user.id
    assert assignment.hostel_id == hostel.id
    assert assignment.assigned_by_id == user.id


def test_rejects_hostel_assignment_for_non_hostel_staff(db, seeded_departments):
    try:
        provision_user(
            db,
            email="it.staff@dau.ac.in",
            name="IT Staff",
            role="staff",
            department_name="IT Services",
            hostel_ids=[1],
            password="SafePassword123!",
        )
    except ValueError as exc:
        assert "Hostel assignments" in str(exc)
    else:
        raise AssertionError("Expected non-Hostel staff assignment to fail")


def test_existing_user_is_unchanged_without_update(db):
    first, created = provision_user(
        db,
        email="repeat@dau.ac.in",
        name="Original Name",
        role="student",
        password="SafePassword123!",
    )
    second, created_again = provision_user(
        db,
        email="repeat@dau.ac.in",
        name="Changed Name",
        role="admin",
        password="DifferentPassword123!",
    )

    assert created is True
    assert created_again is False
    assert second.id == first.id
    assert second.name == "Original Name"
    assert second.role == "student"


def test_rejects_disallowed_domain(db):
    try:
        provision_user(
            db,
            email="person@example.com",
            name="Person",
            role="student",
            password="SafePassword123!",
        )
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("Expected disallowed domain to fail")


def test_update_to_non_staff_clears_old_hostel_assignments(db, seeded_departments):
    hostel = Hostel(code="B", name="Hostel B", is_active=True)
    db.add(hostel)
    db.commit()
    db.refresh(hostel)

    user, _ = provision_user(
        db,
        email="change.role@dau.ac.in",
        name="Changeable User",
        role="staff",
        department_name="Hostel",
        hostel_ids=[hostel.id],
        password="SafePassword123!",
    )
    assert db.query(StaffHostelAssignment).filter_by(user_id=user.id).count() == 1

    provision_user(
        db,
        email="change.role@dau.ac.in",
        name="Changeable User",
        role="admin",
        password="SafePassword123!",
        update=True,
    )

    assert db.query(StaffHostelAssignment).filter_by(user_id=user.id).count() == 0
