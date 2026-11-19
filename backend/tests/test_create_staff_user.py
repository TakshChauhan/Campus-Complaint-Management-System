from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User
from app.scripts.create_staff_user import provision_user


def test_creates_verified_demo_student(db):
    user, created = provision_user(
        db,
        email="demo.student@dau.ac.in",
        name="Demo Student",
        role="student",
        password="SafePassword123!",
    )

    assert created == "created"
    assert user.role == "student"
    assert user.email_verified is True
    assert user.email_verification_required is False
    assert user.department_id is None


def test_creates_hostel_staff_with_assignments(db, seeded_departments):
    admin = User(
        name="Provisioning Admin",
        email="provisioning.admin@dau.ac.in",
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

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
        assigned_by_email=admin.email,
        password="SafePassword123!",
    )

    assert created == "created"
    assert user.department.name == "Hostel"
    assignment = db.query(StaffHostelAssignment).one()
    assert assignment.user_id == user.id
    assert assignment.hostel_id == hostel.id
    assert assignment.assigned_by_id == admin.id


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

    assert created == "created"
    assert created_again == "unchanged"
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
        assert "official campus emails" in str(exc)
    else:
        raise AssertionError("Expected disallowed domain to fail")


def test_rejects_malformed_email(db):
    try:
        provision_user(
            db,
            email="not-an-email",
            name="Person",
            role="student",
            password="SafePassword123!",
        )
    except ValueError as exc:
        assert "email" in str(exc).lower()
    else:
        raise AssertionError("Expected malformed email to fail")


def test_rejects_whitespace_only_password(db):
    try:
        provision_user(
            db,
            email="whitespace.password@dau.ac.in",
            name="Person",
            role="student",
            password="        ",
        )
    except ValueError as exc:
        assert "whitespace" in str(exc).lower()
    else:
        raise AssertionError("Expected whitespace-only password to fail")


def test_rejects_password_over_72_utf8_bytes(db):
    try:
        provision_user(
            db,
            email="long.password@dau.ac.in",
            name="Person",
            role="student",
            password="a" * 73,
        )
    except ValueError as exc:
        assert "72 bytes" in str(exc)
    else:
        raise AssertionError("Expected overlong password to fail")


def test_requires_admin_as_hostel_assignment_actor(db, seeded_departments):
    hostel = Hostel(code="C", name="Hostel C", is_active=True)
    db.add(hostel)
    db.commit()
    db.refresh(hostel)

    try:
        provision_user(
            db,
            email="no.admin@dau.ac.in",
            name="Hostel Staff",
            role="staff",
            department_name="Hostel",
            hostel_ids=[hostel.id],
            assigned_by_email="missing.admin@dau.ac.in",
            password="SafePassword123!",
        )
    except ValueError as exc:
        assert "active admin" in str(exc).lower()
    else:
        raise AssertionError("Expected missing admin assigner to fail")


def test_update_to_non_staff_clears_old_hostel_assignments(db, seeded_departments):
    db.add(User(
        name="Provisioning Admin",
        email="role.change.admin@dau.ac.in",
        role="admin",
        is_active=True,
        email_verified=True,
    ))
    db.commit()

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
        assigned_by_email="role.change.admin@dau.ac.in",
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


def test_department_lookup_is_exact_not_pattern_matching(db, seeded_departments):
    try:
        provision_user(
            db,
            email="pattern.department@dau.ac.in",
            name="Pattern Department",
            role="staff",
            department_name="IT%",
            password="SafePassword123!",
        )
    except ValueError as exc:
        assert "department not found" in str(exc).lower()
    else:
        raise AssertionError("Expected department lookup to treat % as a literal")


def test_update_reports_updated_action(db):
    provision_user(
        db,
        email="update.status@dau.ac.in",
        name="Original Name",
        role="student",
        password="SafePassword123!",
    )

    user, action = provision_user(
        db,
        email="update.status@dau.ac.in",
        name="Updated Name",
        role="student",
        password="SafePassword123!",
        update=True,
    )

    assert action == "updated"
    assert user.name == "Updated Name"
