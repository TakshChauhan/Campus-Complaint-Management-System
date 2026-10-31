"""S3-04: safe canonical complaint-floor backfill."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def test_floor_backfill_is_exact_and_preserves_legacy_location_text(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'complaints.db'}"
    cfg = _config(db_url)
    command.upgrade(cfg, "0009_student_residences")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO departments (id, name) VALUES (1, 'Hostel')"))
        conn.execute(text("INSERT INTO users (id, name, email, role) VALUES (1, 'Student', 's@example.edu', 'student')"))
        conn.execute(text("INSERT INTO hostels (id, code, name) VALUES (1, 'MH', 'Main Hostel')"))
        conn.execute(text("INSERT INTO hostel_wings (id, hostel_id, code, name) VALUES (1, 1, 'B', 'Wing B')"))
        conn.execute(text("INSERT INTO hostel_floors (id, wing_id, code, name) VALUES (7, 1, '2', 'Floor 2')"))
        conn.execute(text("""
            INSERT INTO complaints (id, title, description, department_id, created_by_id, hostel, wing, floor)
            VALUES
              (1, 'Exact', 'd', 1, 1, ' mh ', ' b ', ' 2 '),
              (2, 'Ambiguous', 'd', 1, 1, 'Main Hostel', 'B', 'second floor'),
              (3, 'Unknown', 'd', 1, 1, 'MH', 'Z', '2')
        """))
    engine.dispose()

    command.upgrade(cfg, "0010_complaint_floor_location")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, floor_id, hostel, wing, floor FROM complaints ORDER BY id"
        )).all()
    engine.dispose()

    assert rows == [
        (1, 7, " mh ", " b ", " 2 "),
        (2, None, "Main Hostel", "B", "second floor"),
        (3, None, "MH", "Z", "2"),
    ]
