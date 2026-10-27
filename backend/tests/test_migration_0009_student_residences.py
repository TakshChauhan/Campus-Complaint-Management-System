"""S3-02: student residence schema and migration behavior."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.student_residence import StudentResidence


BACKEND_DIR = Path(__file__).resolve().parents[1]
REV_0008 = "0008_hostel_locations"
REV_0009 = "0009_student_residences"


def _config(db_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_residence_schema_constraints_and_roundtrip(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'residences.db'}"
    config = _config(db_url)
    command.upgrade(config, REV_0008)
    engine = create_engine(db_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO departments (id, name) VALUES (1, 'Hostel')"))
            connection.execute(text(
                "INSERT INTO users (id, name, email, role) VALUES "
                "(1, 'Student', 'student@example.edu', 'student'), "
                "(2, 'Reviewer', 'reviewer@example.edu', 'staff')"
            ))
            connection.execute(text(
                "INSERT INTO complaints (id, title, description, department_id, created_by_id) "
                "VALUES (1, 'Broken tap', 'A tap is broken.', 1, 1)"
            ))
            connection.execute(text("INSERT INTO hostels (id, code, name) VALUES (1, 'OLD_HOR', 'Old HoR')"))
            connection.execute(text(
                "INSERT INTO hostel_wings (id, hostel_id, code, name) VALUES (1, 1, 'B', 'Wing B')"
            ))
            connection.execute(text(
                "INSERT INTO hostel_floors (id, wing_id, code, name) VALUES (1, 1, '2', 'Second Floor')"
            ))

        command.upgrade(config, REV_0009)
        inspector = inspect(engine)
        assert "student_residences" in inspector.get_table_names()
        columns = {column["name"]: column for column in inspector.get_columns("student_residences")}
        assert set(columns) == {
            "id", "student_id", "floor_id", "status", "remark", "verified_by_id",
            "verified_at", "submitted_at", "updated_at",
        }
        assert columns["student_id"]["nullable"] is False
        assert columns["floor_id"]["nullable"] is False
        assert columns["verified_by_id"]["nullable"] is True
        fks = {
            fk["constrained_columns"][0]: (fk["referred_table"], fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys("student_residences")
        }
        assert fks == {
            "student_id": ("users", "RESTRICT"),
            "floor_id": ("hostel_floors", "RESTRICT"),
            "verified_by_id": ("users", "RESTRICT"),
        }
        assert any(
            constraint["column_names"] == ["student_id"]
            for constraint in inspector.get_unique_constraints("student_residences")
        )
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            residence_diffs = [
                diff for diff in compare_metadata(context, Base.metadata)
                if "student_residences" in repr(diff)
            ]
        assert residence_diffs == []

        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text(
                "INSERT INTO student_residences (id, student_id, floor_id) VALUES (1, 1, 1)"
            ))
            row = connection.execute(text(
                "SELECT status, remark, verified_by_id, verified_at, submitted_at "
                "FROM student_residences WHERE id = 1"
            )).one()
            assert row.status == "pending"
            assert row.remark is None and row.verified_by_id is None and row.verified_at is None
            assert row.submitted_at is not None

        with Session(engine) as session:
            residence = session.get(StudentResidence, 1)
            assert residence.student.email == "student@example.edu"
            assert residence.floor.wing.hostel.name == "Old HoR"
            assert residence.student.residence is residence

        invalid_statements = [
            "INSERT INTO student_residences (student_id, floor_id) VALUES (1, 1)",
            "INSERT INTO student_residences (student_id, floor_id) VALUES (999, 1)",
            "INSERT INTO student_residences (student_id, floor_id) VALUES (2, 999)",
            "INSERT INTO student_residences (student_id, floor_id, status) VALUES (2, 1, 'approved')",
            "DELETE FROM hostel_floors WHERE id = 1",
        ]
        for statement in invalid_statements:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
                with pytest.raises(IntegrityError):
                    connection.execute(text(statement))

        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text(
                "UPDATE student_residences SET status = 'verified', verified_by_id = 2, "
                "verified_at = CURRENT_TIMESTAMP WHERE id = 1"
            ))
        with Session(engine) as session:
            residence = session.get(StudentResidence, 1)
            assert residence.verified_by.name == "Reviewer"
            assert residence.status == "verified"

        command.downgrade(config, REV_0008)
        assert "student_residences" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT title FROM complaints WHERE id = 1")).scalar_one() == "Broken tap"
            assert connection.execute(text("SELECT name FROM hostel_floors WHERE id = 1")).scalar_one() == "Second Floor"

        command.upgrade(config, REV_0009)
        assert "student_residences" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
