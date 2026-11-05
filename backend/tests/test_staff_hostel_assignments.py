from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User
from app.repositories.staff_hostel_assignment_repository import get_hostels_for_staff, get_staff_for_hostel

BACKEND_DIR = Path(__file__).resolve().parents[1]

def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg

def test_migration_upgrade_creates_complete_schema_and_downgrade_removes_it(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'assignments.db'}"
    cfg = _config(db_url)
    command.upgrade(cfg, "0014_staff_hostel_assignments")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    assert "staff_hostel_assignments" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("staff_hostel_assignments")} == {"id", "user_id", "hostel_id", "assigned_by_id", "created_at"}
    assert [constraint["name"] for constraint in inspector.get_unique_constraints("staff_hostel_assignments")] == ["uq_staff_hostel_assignments_user_hostel"]
    foreign_keys = {(fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0], fk["options"]["ondelete"]) for fk in inspector.get_foreign_keys("staff_hostel_assignments")}
    assert foreign_keys == {("user_id", "users", "id", "RESTRICT"), ("hostel_id", "hostels", "id", "RESTRICT"), ("assigned_by_id", "users", "id", "RESTRICT")}
    command.downgrade(cfg, "0013_backfill_complaint_floor_ids")
    assert "staff_hostel_assignments" not in inspect(engine).get_table_names()
    engine.dispose()

def test_foreign_keys_prevent_deleting_assigned_records(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'restrict.db'}"
    cfg = _config(db_url)
    command.upgrade(cfg, "0014_staff_hostel_assignments")
    engine = create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("INSERT INTO users (id, name, email, role) VALUES (1, 'Staff', 's@e.edu', 'staff')"))
        connection.execute(text("INSERT INTO users (id, name, email, role) VALUES (2, 'Admin', 'a@e.edu', 'admin')"))
        connection.execute(text("INSERT INTO hostels (id, code, name) VALUES (1, 'H1', 'Hostel 1')"))
        connection.execute(text("INSERT INTO staff_hostel_assignments (user_id, hostel_id, assigned_by_id) VALUES (1, 1, 2)"))
        for statement in ("DELETE FROM users WHERE id = 1", "DELETE FROM users WHERE id = 2", "DELETE FROM hostels WHERE id = 1"):
            with pytest.raises(IntegrityError):
                connection.execute(text(statement))
    engine.dispose()

def test_repository_lookups_return_assignments_and_empty_results(db):
    staff = User(name="Staff", email="staff.assign@example.edu", role="staff")
    admin = User(name="Admin", email="admin.assign@example.edu", role="admin")
    other = User(name="Other", email="other.assign@example.edu", role="staff")
    hostel_a, hostel_b = Hostel(code="HA", name="Hostel A"), Hostel(code="HB", name="Hostel B")
    db.add_all([staff, admin, other, hostel_a, hostel_b])
    db.flush()
    db.add_all([StaffHostelAssignment(user_id=staff.id, hostel_id=hostel_a.id, assigned_by_id=admin.id), StaffHostelAssignment(user_id=staff.id, hostel_id=hostel_b.id, assigned_by_id=admin.id), StaffHostelAssignment(user_id=other.id, hostel_id=hostel_a.id, assigned_by_id=admin.id)])
    db.commit()
    assert [hostel.code for hostel in get_hostels_for_staff(db, staff.id)] == ["HA", "HB"]
    assert [user.email for user in get_staff_for_hostel(db, hostel_a.id)] == [staff.email, other.email]
    assert get_hostels_for_staff(db, 99999) == []
    assert get_staff_for_hostel(db, 99999) == []

def test_assignment_unique_constraint_rejects_duplicate_pair(db):
    staff = User(name="Staff", email="unique.staff@example.edu", role="staff")
    admin = User(name="Admin", email="unique.admin@example.edu", role="admin")
    hostel = Hostel(code="HU", name="Unique Hostel")
    db.add_all([staff, admin, hostel])
    db.flush()
    db.add(StaffHostelAssignment(user_id=staff.id, hostel_id=hostel.id, assigned_by_id=admin.id))
    db.commit()
    db.add(StaffHostelAssignment(user_id=staff.id, hostel_id=hostel.id, assigned_by_id=admin.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
