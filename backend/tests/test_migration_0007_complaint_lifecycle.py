"""Migration 0007 (complaint lifecycle fields + status history) on fresh local databases.

SQLite tests always run. The PostgreSQL test runs only when CCMS_DISPOSABLE_TEST_POSTGRES_URL
points at a dedicated, empty test database on a loopback host (its name must contain
"test"). It refuses to touch a populated database, and afterwards downgrades to base
so the database is empty again; it never drops a schema.
"""
import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, IntegrityError

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REV_0006 = "0006_user_external_identity_user_provider_uq"
REV_0007 = "0007_complaint_lifecycle"
NEW_COLUMNS = {"is_public", "hostel", "wing", "floor", "updated_at", "resolved_at", "reopen_count"}
ORIGINAL_COLUMNS = ["id", "title", "description", "department_id", "created_by_id", "status", "created_at"]


def _config(db_url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return cfg


def _version(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _complaint_rows(engine):
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT {', '.join(ORIGINAL_COLUMNS)} FROM complaints ORDER BY id")
        ).fetchall()


def _schema_snapshot(engine):
    insp = inspect(engine)
    indexes = sorted((i["name"], tuple(i["column_names"])) for i in insp.get_indexes("complaints"))
    fks = sorted(
        (tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
        for fk in insp.get_foreign_keys("complaints")
    )
    return indexes, fks


def _seed_pre_0007_rows(engine, true_literal: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO departments (id, name, is_active) VALUES (1, 'Hostel', {true_literal})"))
        conn.execute(text(
            "INSERT INTO users (id, name, email, password_hash, role, is_active) "
            f"VALUES (1, 'Existing Student', 'existing.student@dau.ac.in', 'hash', 'student', {true_literal})"
        ))
        conn.execute(text(
            "INSERT INTO complaints (id, title, description, department_id, created_by_id, status, created_at) "
            "VALUES (10, 'Fan broken', 'The ceiling fan in my room stopped working.', 1, 1, 'submitted', "
            "'2026-09-01 10:00:00+00:00')"
        ))
        # Sprint 1 had no status-change endpoint, but a manually edited row must still migrate.
        conn.execute(text(
            "INSERT INTO complaints (id, title, description, department_id, created_by_id, status, created_at) "
            "VALUES (11, 'Tap leaking', 'The washroom tap leaks all night long.', 1, 1, 'in_progress', "
            "'2026-09-02 11:30:00+00:00')"
        ))


def test_fresh_upgrade_creates_columns_defaults_indexes_and_foreign_keys(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    command.upgrade(_config(url), REV_0007)
    engine = create_engine(url)
    try:
        assert _version(engine) == REV_0007
        insp = inspect(engine)

        columns = {c["name"]: c for c in insp.get_columns("complaints")}
        assert NEW_COLUMNS <= columns.keys()
        for name in ("is_public", "updated_at", "reopen_count"):
            assert columns[name]["nullable"] is False
        for name in ("hostel", "wing", "floor", "resolved_at"):
            assert columns[name]["nullable"] is True
        assert "false" in str(columns["is_public"]["default"]).lower()
        assert str(columns["reopen_count"]["default"]).strip("'\"") == "0"
        assert columns["updated_at"]["default"] is not None

        history_columns = {c["name"]: c for c in insp.get_columns("complaint_status_history")}
        assert set(history_columns) == {"id", "complaint_id", "from_status", "to_status", "actor_id", "remark", "created_at"}
        assert history_columns["from_status"]["nullable"] is True
        for name in ("complaint_id", "to_status", "actor_id", "created_at"):
            assert history_columns[name]["nullable"] is False

        history_indexes = {i["name"]: i["column_names"] for i in insp.get_indexes("complaint_status_history")}
        assert history_indexes["ix_complaint_status_history_complaint_id"] == ["complaint_id"]

        history_fks = {
            fk["constrained_columns"][0]: (fk["referred_table"], fk["options"].get("ondelete"))
            for fk in insp.get_foreign_keys("complaint_status_history")
        }
        assert history_fks == {"complaint_id": ("complaints", "RESTRICT"), "actor_id": ("users", "RESTRICT")}

        # Sprint 1 indexes and foreign keys on complaints survive the table rebuild.
        indexes, fks = _schema_snapshot(engine)
        assert ("ix_complaints_created_by_id_created_at", ("created_by_id", "created_at")) in indexes
        assert (("created_by_id",), "users", "RESTRICT") in fks
        assert (("department_id",), "departments", "RESTRICT") in fks
    finally:
        engine.dispose()


def test_upgrade_preserves_existing_complaints_and_backfills_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    cfg = _config(url)
    command.upgrade(cfg, REV_0006)
    engine = create_engine(url)
    try:
        _seed_pre_0007_rows(engine, "1")
        rows_before = _complaint_rows(engine)
        schema_before = _schema_snapshot(engine)

        command.upgrade(cfg, REV_0007)

        assert _complaint_rows(engine) == rows_before
        assert _schema_snapshot(engine) == schema_before
        with engine.connect() as conn:
            lifecycle = conn.execute(text(
                "SELECT id, is_public, hostel, wing, floor, resolved_at, reopen_count, updated_at = created_at "
                "FROM complaints ORDER BY id"
            )).fetchall()
            assert [tuple(r) for r in lifecycle] == [
                (10, 0, None, None, None, None, 0, 1),
                (11, 0, None, None, None, None, 0, 1),
            ]

            history = conn.execute(text(
                "SELECT h.complaint_id, h.from_status, h.to_status, h.actor_id, h.remark, "
                "h.created_at = c.created_at "
                "FROM complaint_status_history h JOIN complaints c ON c.id = h.complaint_id "
                "ORDER BY h.complaint_id"
            )).fetchall()
        assert len(history) == 2
        submitted, snapshot = history
        # A submitted complaint's creation is its real first event.
        assert tuple(submitted) == (10, None, "submitted", 1, None, 1)
        # Other statuses are a labelled snapshot; no earlier transitions are invented.
        assert snapshot[:4] == (11, None, "in_progress", 1)
        assert "earlier transitions unavailable" in snapshot[4]
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade_keep_complaints_intact(tmp_path):
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    cfg = _config(url)
    command.upgrade(cfg, REV_0006)
    engine = create_engine(url)
    try:
        _seed_pre_0007_rows(engine, "1")
        rows_before = _complaint_rows(engine)
        schema_before = _schema_snapshot(engine)

        command.upgrade(cfg, REV_0007)
        command.downgrade(cfg, "-1")

        assert _version(engine) == REV_0006
        insp = inspect(engine)
        assert "complaint_status_history" not in insp.get_table_names()
        assert [c["name"] for c in insp.get_columns("complaints")] == ORIGINAL_COLUMNS
        assert _complaint_rows(engine) == rows_before
        assert _schema_snapshot(engine) == schema_before

        command.upgrade(cfg, REV_0007)
        assert _version(engine) == REV_0007
        assert _complaint_rows(engine) == rows_before
        with engine.connect() as conn:
            # Backfill runs once per upgrade: exactly one history row per complaint.
            counts = conn.execute(text(
                "SELECT complaint_id, COUNT(*) FROM complaint_status_history GROUP BY complaint_id ORDER BY complaint_id"
            )).fetchall()
        assert [tuple(r) for r in counts] == [(10, 1), (11, 1)]
    finally:
        engine.dispose()


def test_history_foreign_keys_restrict_deletes(tmp_path):
    url = f"sqlite:///{tmp_path / 'fk.db'}"
    cfg = _config(url)
    command.upgrade(cfg, REV_0006)
    engine = create_engine(url)
    try:
        _seed_pre_0007_rows(engine, "1")
        command.upgrade(cfg, REV_0007)
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            with pytest.raises(IntegrityError):
                conn.execute(text("DELETE FROM complaints WHERE id = 10"))
            conn.rollback()
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO complaint_status_history (complaint_id, to_status, actor_id) "
                    "VALUES (999, 'submitted', 1)"
                ))
            conn.rollback()
            assert conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar_one() == 2
    finally:
        engine.dispose()


def test_migrated_lifecycle_tables_match_orm_models(tmp_path):
    """No autogenerate drift for the tables migration 0007 touches."""
    from app.db.base import Base

    url = f"sqlite:///{tmp_path / 'drift.db'}"
    command.upgrade(_config(url), "head")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            diffs = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    def touches_lifecycle(diff) -> bool:
        flat = diff if isinstance(diff, list) else [diff]
        return any("complaint" in repr(item) for item in flat)

    assert [d for d in diffs if touches_lifecycle(d)] == []


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
RESERVED_DATABASES = {"postgres", "template0", "template1"}


def _disposable_postgres_url_problem(raw_url: str) -> str | None:
    """Return why raw_url is not a dedicated local test database, or None if it is."""
    try:
        url = make_url(raw_url)
    except ArgumentError:
        return "URL cannot be parsed"
    if url.get_backend_name() != "postgresql":
        return f"backend is {url.get_backend_name()!r}, not postgresql"
    # libpq lets query parameters override the host, so they must not be present.
    if {"host", "hostaddr", "service"} & {key.lower() for key in url.query}:
        return "host/hostaddr/service query parameters are not allowed"
    if (url.host or "").lower() not in LOOPBACK_HOSTS:
        return f"host {url.host!r} is not a loopback address"
    database = url.database or ""
    if database in RESERVED_DATABASES or "test" not in database.lower():
        return f"database {database!r} is not a dedicated test database (its name must contain 'test')"
    return None


@pytest.mark.parametrize("raw_url, allowed", [
    ("postgresql+psycopg://u:p@localhost:5432/ccms_migration_test", True),
    ("postgresql://u:p@127.0.0.1/ccms_test", True),
    ("postgresql://u:p@[::1]:5432/ccms_test", True),
    ("postgresql://u:p@db.abc.supabase.co:5432/ccms_test", False),
    ("postgresql://u:p@localhost.evil.example/ccms_test", False),
    ("postgresql://u:p@127.0.0.1.nip.io/ccms_test", False),
    ("postgresql://localhost:p@db.example.com/ccms_test", False),
    ("postgresql://u:p@localhost/ccms_test?host=db.example.com", False),
    ("postgresql://u:p@localhost/postgres", False),
    ("postgresql://u:p@localhost/ccms", False),
    ("postgresql:///ccms_test", False),
    ("sqlite:///ccms_test.db", False),
])
def test_disposable_postgres_url_guard(raw_url, allowed):
    assert (_disposable_postgres_url_problem(raw_url) is None) is allowed


def _user_tables(engine) -> list[str]:
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT table_schema || '.' || table_name FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "AND table_schema NOT LIKE 'pg_toast%' AND table_schema NOT LIKE 'pg_temp%'"
        )).scalars().all()


@pytest.mark.skipif(
    not os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL"),
    reason="Set CCMS_DISPOSABLE_TEST_POSTGRES_URL to a dedicated, empty, local PostgreSQL test database",
)
def test_postgresql_upgrade_downgrade_roundtrip():
    url = os.environ["CCMS_DISPOSABLE_TEST_POSTGRES_URL"]
    problem = _disposable_postgres_url_problem(url)
    if problem:
        pytest.fail(f"Refusing to use CCMS_DISPOSABLE_TEST_POSTGRES_URL: {problem}")

    engine = create_engine(url)
    existing = _user_tables(engine)
    if existing:
        engine.dispose()
        pytest.fail(
            "Refusing to modify a populated database; CCMS_DISPOSABLE_TEST_POSTGRES_URL must point at an "
            f"empty database. Found: {', '.join(sorted(existing)[:10])}"
        )

    cfg = _config(url)
    try:
        # env.py only widens alembic_version.version_num when the table already
        # exists, so a brand-new PostgreSQL database must stop before 0006.
        command.upgrade(cfg, "0005_email_verification_tokens")
        command.upgrade(cfg, REV_0006)
        _seed_pre_0007_rows(engine, "true")
        rows_before = _complaint_rows(engine)
        schema_before = _schema_snapshot(engine)

        command.upgrade(cfg, REV_0007)
        assert _complaint_rows(engine) == rows_before
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM complaint_status_history")).scalar_one() == 2
            assert conn.execute(text(
                "SELECT COUNT(*) FROM complaints WHERE updated_at = created_at AND is_public = false AND reopen_count = 0"
            )).scalar_one() == 2

        command.downgrade(cfg, "-1")
        assert _version(engine) == REV_0006
        assert "complaint_status_history" not in inspect(engine).get_table_names()
        assert _complaint_rows(engine) == rows_before
        assert _schema_snapshot(engine) == schema_before

        command.upgrade(cfg, REV_0007)
        assert _version(engine) == REV_0007
        assert _complaint_rows(engine) == rows_before
    finally:
        # Remove only what this test created, leaving the database empty for the next run.
        # If this fails, the database stays populated and later runs refuse to use it.
        try:
            command.downgrade(cfg, "base")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        finally:
            engine.dispose()
