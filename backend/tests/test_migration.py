import os
import sqlite3
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _get_alembic_config(db_url: str) -> Config:
    alembic_ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option(
        "script_location",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic"))
    )
    return alembic_cfg


def test_alembic_upgrade_and_downgrade(tmp_path):
    """Verify that Alembic migrations run cleanly up, down, and up again on a target database."""
    test_db_file = tmp_path / "migration_test.db"
    test_db_url = f"sqlite:///{test_db_file}"
    alembic_cfg = _get_alembic_config(test_db_url)

    # 1. Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables created
    engine = create_engine(test_db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "departments" in tables
    assert "complaints" in tables
    assert "user_external_identities" in tables
    assert "oauth_transactions" in tables
    assert "oauth_handoff_tickets" in tables
    assert "alembic_version" in tables

    # Verify composite index on complaints
    indexes = inspector.get_indexes("complaints")
    index_names = [idx["name"] for idx in indexes]
    assert "ix_complaints_created_by_id_created_at" in index_names

    # Behavioral test: check constraint rejects invalid role
    with engine.connect() as conn:
        # Valid role works
        conn.execute(
            text("INSERT INTO users (name, email, password_hash, role, is_active) VALUES (:name, :email, :pw, :role, :active)"),
            {"name": "Valid User", "email": "valid@campus.edu", "pw": "hash123", "role": "student", "active": 1}
        )
        conn.commit()

        # Invalid role must violate ck_users_role
        with pytest.raises(IntegrityError):
            conn.execute(
                text("INSERT INTO users (name, email, password_hash, role, is_active) VALUES (:name, :email, :pw, :role, :active)"),
                {"name": "Invalid Role User", "email": "invalid@campus.edu", "pw": "hash123", "role": "superadmin", "active": 1}
            )
            conn.commit()

        # Nullable password_hash works for Google OAuth users
        conn.execute(
            text("INSERT INTO users (name, email, password_hash, role, is_active, email_verified) VALUES (:name, :email, NULL, :role, :active, 1)"),
            {"name": "Google User", "email": "google.student@campus.edu", "role": "student", "active": 1}
        )
        conn.commit()

    # 2. Run downgrade back to base
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    tables_after_downgrade = inspector.get_table_names()
    assert "users" not in tables_after_downgrade
    assert "departments" not in tables_after_downgrade
    assert "complaints" not in tables_after_downgrade
    assert "user_external_identities" not in tables_after_downgrade

    # 3. Upgrade again to head (complete cycle verification)
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(engine)
    tables_after_second_upgrade = inspector.get_table_names()
    assert "users" in tables_after_second_upgrade
    assert "complaints" in tables_after_second_upgrade
    assert "oauth_transactions" in tables_after_second_upgrade


def test_migration_compatibility_with_legacy_revisions(tmp_path):
    """
    Test compatibility with all 4 supported database revision states:
    1. Fresh database.
    2. Database at 0001_initial_sprint1.
    3. Database at 0002_history_idx_role_check (shortened revision).
    4. Database at 0002_history_index_and_role_check (legacy 33-char revision).
    """
    # State 1: Fresh DB
    db1 = tmp_path / "fresh.db"
    cfg1 = _get_alembic_config(f"sqlite:///{db1}")
    command.upgrade(cfg1, "head")
    tables1 = inspect(create_engine(f"sqlite:///{db1}")).get_table_names()
    assert "user_external_identities" in tables1

    # State 2: Database at 0001
    db2 = tmp_path / "at_0001.db"
    cfg2 = _get_alembic_config(f"sqlite:///{db2}")
    command.upgrade(cfg2, "0001_initial_sprint1")
    command.upgrade(cfg2, "head")
    tables2 = inspect(create_engine(f"sqlite:///{db2}")).get_table_names()
    assert "oauth_transactions" in tables2

    # State 3: Database at 0002 shortened
    db3 = tmp_path / "at_0002_short.db"
    cfg3 = _get_alembic_config(f"sqlite:///{db3}")
    command.upgrade(cfg3, "0002_history_idx_role_check")
    command.upgrade(cfg3, "head")
    tables3 = inspect(create_engine(f"sqlite:///{db3}")).get_table_names()
    assert "oauth_handoff_tickets" in tables3

    # State 4: Database recording legacy long 0002 identifier (33 characters)
    db4 = tmp_path / "at_0002_legacy_long.db"
    cfg4 = _get_alembic_config(f"sqlite:///{db4}")
    command.upgrade(cfg4, "0002_history_idx_role_check")
    with sqlite3.connect(str(db4)) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '0002_history_index_and_role_check';")
        conn.commit()

    # Upgrade to head must cleanly reconcile without error or multiple heads
    command.upgrade(cfg4, "head")
    tables4 = inspect(create_engine(f"sqlite:///{db4}")).get_table_names()
    assert "user_external_identities" in tables4
    assert "oauth_transactions" in tables4

    # Verify version record is now at head
    with sqlite3.connect(str(db4)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT version_num FROM alembic_version;")
        head_rev = cur.fetchone()[0]
        assert head_rev == "0007_complaint_lifecycle"
