"""S3-01: hostel location hierarchy and migration behavior."""

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
from app.models.hostel_floor import HostelFloor


BACKEND_DIR = Path(__file__).resolve().parents[1]
REV_0007 = "0007_complaint_lifecycle"
REV_0008 = "0008_hostel_locations"


def _config(db_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_hostel_hierarchy_constraints_and_roundtrip(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'locations.db'}"
    config = _config(db_url)
    command.upgrade(config, REV_0007)
    engine = create_engine(db_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO departments (id, name) VALUES (1, 'Hostel')"))
            connection.execute(text(
                "INSERT INTO users (id, name, email, role) "
                "VALUES (1, 'Student', 'student@example.edu', 'student')"
            ))
            connection.execute(text(
                "INSERT INTO complaints (id, title, description, department_id, created_by_id) "
                "VALUES (1, 'Broken tap', 'A tap is broken.', 1, 1)"
            ))

        command.upgrade(config, REV_0008)
        inspector = inspect(engine)
        assert {"hostels", "hostel_wings", "hostel_floors"} <= set(inspector.get_table_names())
        assert inspector.get_foreign_keys("hostel_wings")[0]["referred_table"] == "hostels"
        assert inspector.get_foreign_keys("hostel_floors")[0]["referred_table"] == "hostel_wings"
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            location_diffs = [
                diff for diff in compare_metadata(context, Base.metadata)
                if not (diff[0] == "add_table" and diff[1].name == "student_residences")
                if any(table in repr(diff) for table in ("hostels", "hostel_wings", "hostel_floors"))
            ]
        assert location_diffs == []

        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text(
                "INSERT INTO hostels (id, code, name) "
                "VALUES (1, 'OLD_HOR_MEN', 'Old HoR Men'), (2, 'NEW_HOR_MEN', 'New HoR Men')"
            ))
            connection.execute(text(
                "INSERT INTO hostel_wings (id, hostel_id, code, name) "
                "VALUES (1, 1, 'B', 'Wing B'), (2, 2, 'C', 'Wing C')"
            ))
            connection.execute(text(
                "INSERT INTO hostel_floors (id, wing_id, code, name) "
                "VALUES (1, 1, '2', '2nd floor'), (2, 2, '2', '2nd floor')"
            ))
            location = connection.execute(text(
                "SELECT h.name, w.name, f.name, h.is_active, w.is_active, f.is_active "
                "FROM hostel_floors f JOIN hostel_wings w ON w.id = f.wing_id "
                "JOIN hostels h ON h.id = w.hostel_id WHERE f.id = 1"
            )).one()
            assert tuple(location) == ("Old HoR Men", "Wing B", "2nd floor", 1, 1, 1)

        with Session(engine) as session:
            floor = session.get(HostelFloor, 1)
            assert floor.wing.hostel.name == "Old HoR Men"
            assert floor.wing.code == "B"

        # Database constraints must reject malformed names/codes and orphaned
        # parents on SQLite, in addition to the duplicate cases above.
        invalid_statements = [
            "INSERT INTO hostels (code, name) VALUES ('OLD_HOR_MEN', 'Duplicate')",
            "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (2, 'B', 'Duplicate Wing B')",
            "INSERT INTO hostel_floors (wing_id, code, name) VALUES (1, '2', 'Duplicate Floor 2')",
            "INSERT INTO hostels (code, name) VALUES ('', 'Empty hostel code')",
            "INSERT INTO hostels (code, name) VALUES ('TEST', '   ')",
            "INSERT INTO hostels (code, name) VALUES (' lower ', 'Noncanonical code')",
            "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (1, '', 'Empty wing code')",
            "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (1, 'D', '   ')",
            "INSERT INTO hostel_floors (wing_id, code, name) VALUES (1, '', 'Empty floor code')",
            "INSERT INTO hostel_floors (wing_id, code, name) VALUES (1, '3', '   ')",
            "INSERT INTO hostel_floors (wing_id, code, name) VALUES (1, 'g', 'Lowercase code')",
            "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (999, 'Z', 'Missing hostel')",
            "INSERT INTO hostel_floors (wing_id, code, name) VALUES (999, 'G', 'Missing wing')",
            "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (1, 'b', 'Lowercase code')",
            "DELETE FROM hostel_wings WHERE id = 1",
            "DELETE FROM hostels WHERE id = 1",
        ]
        for statement in invalid_statements:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
                with pytest.raises(IntegrityError):
                    connection.execute(text(statement))

        command.downgrade(config, REV_0007)
        assert not {"hostels", "hostel_wings", "hostel_floors"} & set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("SELECT title FROM complaints WHERE id = 1")).scalar_one() == "Broken tap"

        command.upgrade(config, REV_0008)
        assert {"hostels", "hostel_wings", "hostel_floors"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
