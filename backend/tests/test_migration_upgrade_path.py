"""Upgrade-path regression tests for the Alembic history.

Databases created from `main` before the Sprint 1 final sync are recorded at
revision `0004_restrict_complaint_delete`. They must upgrade to head without
manual stamping and without losing rows.
"""
import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRE_SYNC_REVISION = "0004_restrict_complaint_delete"


def _config(db_url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return cfg


def _recorded_version(db_url: str) -> str:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


def test_history_has_single_head_and_pre_sync_revision():
    script = ScriptDirectory.from_config(_config("sqlite://"))
    assert len(script.get_heads()) == 1
    assert script.get_revision(PRE_SYNC_REVISION) is not None


def test_database_at_pre_sync_0004_upgrades_to_head_and_keeps_rows(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'pre_sync.db'}"
    cfg = _config(db_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()

    command.upgrade(cfg, PRE_SYNC_REVISION)
    assert _recorded_version(db_url) == PRE_SYNC_REVISION

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO departments (name, is_active) VALUES ('Hostel', 1)"))
        conn.execute(text(
            "INSERT INTO users (name, email, password_hash, role, is_active) "
            "VALUES ('Existing Student', 'existing@dau.ac.in', 'hash', 'student', 1)"
        ))
        conn.execute(text(
            "INSERT INTO complaints (title, description, department_id, created_by_id, status) "
            "VALUES ('Fan broken', 'The ceiling fan in my room stopped working.', 1, 1, 'submitted')"
        ))
    engine.dispose()

    command.upgrade(cfg, "head")
    assert _recorded_version(db_url) == head

    engine = create_engine(db_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar_one() == 1
    engine.dispose()

    # Running the upgrade again is a no-op.
    command.upgrade(cfg, "head")
    assert _recorded_version(db_url) == head
