"""Migrations 0011 (public feed / HMC) and 0012 (explicit HMC audiences)."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
REV_0010 = "0010_complaint_floor_location"
REV_0011 = "0011_public_feed_hmc"
REV_0012 = "0012_complaint_hmc_audiences"
NEW_TABLES = {"hmc_groups", "hmc_group_floors", "hmc_group_moderators", "complaint_publication_audit"}
NEW_COMPLAINT_COLUMNS = {
    "visibility_scope", "feed_review_status", "publication_status",
    "feed_reviewed_by_id", "feed_reviewed_at", "feed_review_note",
}


def _config(db_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def _seed_at_0010(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO departments (id, name) VALUES (1, 'Hostel'), (2, 'IT Services')"))
        conn.execute(text(
            "INSERT INTO users (id, name, email, role) VALUES "
            "(1, 'Student', 's@example.edu', 'student'), (2, 'Admin', 'a@example.edu', 'admin')"
        ))
        conn.execute(text("INSERT INTO hostels (id, code, name) VALUES (1, 'MH', 'Main Hostel')"))
        conn.execute(text(
            "INSERT INTO hostel_wings (id, hostel_id, code, name) VALUES (1, 1, 'A', 'Wing A'), (2, 1, 'B', 'Wing B')"
        ))
        conn.execute(text(
            "INSERT INTO hostel_floors (id, wing_id, code, name) VALUES "
            "(1, 1, '1', 'Floor 1'), (2, 2, '1', 'Floor 1'), (3, 1, '2', 'Floor 2')"
        ))
        rows = [
            # id, department, is_public, legacy hostel text, canonical floor
            (1, 2, True, None, None),     # IT, unlocated public       -> published department feed
            (2, 1, True, None, None),     # Hostel, unlocated public   -> pending_mapping
            (3, 2, True, "Block B", None),  # IT, legacy text location -> pending_mapping
            (4, 2, True, None, 1),        # IT, canonical floor        -> pending_mapping
            (5, 2, False, None, None),    # private                    -> private
            (6, 1, False, "Block B", 1),  # private located            -> private
        ]
        for cid, dep, public, hostel, floor in rows:
            conn.execute(text(
                "INSERT INTO complaints (id, title, description, department_id, created_by_id, is_public, hostel, floor_id) "
                "VALUES (:id, 'Title', 'A description.', :dep, 1, :public, :hostel, :floor)"
            ), {"id": cid, "dep": dep, "public": public, "hostel": hostel, "floor": floor})


def test_history_is_linear_with_a_single_head():
    script = ScriptDirectory.from_config(_config("sqlite://"))
    assert script.get_heads() == [REV_0012]
    chain = [rev.revision for rev in script.walk_revisions("base", "heads")][:5]
    assert chain == [REV_0012, REV_0011, REV_0010, "0009_student_residences", "0008_hostel_locations"]


def test_upgrade_backfills_conservatively_and_matches_the_orm(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'feed.db'}"
    config = _config(db_url)
    command.upgrade(config, REV_0010)
    engine = create_engine(db_url)
    try:
        _seed_at_0010(engine)
        command.upgrade(config, "head")
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, visibility_scope, feed_review_status, publication_status FROM complaints ORDER BY id"
            )).all()
        assert [tuple(r) for r in rows] == [
            (1, "department_public", "not_required", "published"),
            (2, "hmc_group_public", "pending", "pending_mapping"),
            (3, "hmc_group_public", "pending", "pending_mapping"),
            (4, "hmc_group_public", "pending", "pending_mapping"),
            (5, "private", "not_required", "private"),
            (6, "private", "not_required", "private"),
        ]

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert NEW_TABLES | {"complaint_hmc_audiences"} <= tables
        # No competing physical hierarchy and no residence columns on users.
        assert not {"buildings", "floors", "wings", "hmc_group_wings"} & tables
        assert not {c["name"] for c in inspector.get_columns("users")} & {
            "residence_building_id", "residence_floor_id", "wing_id", "residence_verified_at",
        }
        fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("hmc_group_floors")}
        assert fk_targets == {"hmc_groups", "hostel_floors"}
        assert {fk["referred_table"] for fk in inspector.get_foreign_keys("hmc_groups")} == {"hostels"}
        assert {fk["name"] for fk in inspector.get_foreign_keys("complaints")} >= {
            "fk_complaints_floor_id_hostel_floors", "fk_complaints_feed_reviewed_by_id_users",
        }

        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            watched = NEW_TABLES | {"complaint_hmc_audiences", "complaints"}
            diffs = [
                diff for diff in compare_metadata(context, Base.metadata)
                if any(f"'{table}'" in repr(diff) or f"{table}." in repr(diff) or f"<{table}>" in repr(diff) for table in watched)
            ]
        assert diffs == []
    finally:
        engine.dispose()


def test_database_constraints_enforce_publication_and_mapping_rules(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'constraints.db'}"
    config = _config(db_url)
    command.upgrade(config, REV_0010)
    engine = create_engine(db_url)
    try:
        _seed_at_0010(engine)
        command.upgrade(config, "head")
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text("INSERT INTO hmc_groups (id, name, hostel_id, floor_code) VALUES (1, 'G1', 1, '1'), (2, 'G2', 1, '2')"))
            conn.execute(text("INSERT INTO hmc_group_floors (hmc_group_id, floor_id) VALUES (1, 1), (1, 2), (2, 3)"))
            conn.execute(text(
                "INSERT INTO complaint_hmc_audiences (complaint_id, hmc_group_id, source, decided_by_id) "
                "VALUES (4, 1, 'responsible_group', 2)"
            ))
        invalid = [
            # department-wide scope cannot carry a location
            "UPDATE complaints SET visibility_scope = 'department_public' WHERE id = 4",
            "UPDATE complaints SET visibility_scope = 'department_public' WHERE id = 3",
            # scope must agree with is_public
            "UPDATE complaints SET visibility_scope = 'private' WHERE id = 1",
            "UPDATE complaints SET visibility_scope = 'hmc_group_public' WHERE id = 5",
            "UPDATE complaints SET publication_status = 'visible' WHERE id = 1",
            "UPDATE complaints SET feed_review_status = 'maybe' WHERE id = 1",
            # one group per canonical floor
            "INSERT INTO hmc_group_floors (hmc_group_id, floor_id) VALUES (2, 1)",
            "INSERT INTO hmc_group_floors (hmc_group_id, floor_id) VALUES (1, 999)",
            "INSERT INTO hmc_groups (name, hostel_id, floor_code) VALUES ('G1', 1, '3')",
            "INSERT INTO hmc_groups (name, hostel_id, floor_code) VALUES ('Lower', 1, 'a')",
            "INSERT INTO hmc_groups (name, hostel_id, floor_code) VALUES ('Nohostel', 999, '1')",
            # one audience row per complaint/group, known sources, real complaints
            "INSERT INTO complaint_hmc_audiences (complaint_id, hmc_group_id, source, decided_by_id) VALUES (4, 1, 'shared_floor', 2)",
            "INSERT INTO complaint_hmc_audiences (complaint_id, hmc_group_id, source, decided_by_id) VALUES (4, 2, 'everyone', 2)",
            "INSERT INTO complaint_hmc_audiences (complaint_id, hmc_group_id, source, decided_by_id) VALUES (999, 2, 'shared_floor', 2)",
            # complaints with publication history cannot be deleted
            "DELETE FROM complaints WHERE id = 4",
            # canonical floors referenced by a group cannot be deleted
            "DELETE FROM hostel_floors WHERE id = 3",
        ]
        for statement in invalid:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA foreign_keys=ON"))
                with pytest.raises(IntegrityError):
                    conn.execute(text(statement))
                conn.rollback()
    finally:
        engine.dispose()


def test_downgrades_remove_only_their_own_schema_and_keep_rows(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    config = _config(db_url)
    command.upgrade(config, REV_0010)
    engine = create_engine(db_url)
    try:
        _seed_at_0010(engine)
        command.upgrade(config, "head")

        command.downgrade(config, REV_0011)
        inspector = inspect(engine)
        assert "complaint_hmc_audiences" not in inspector.get_table_names()
        assert NEW_TABLES <= set(inspector.get_table_names())

        command.downgrade(config, REV_0010)
        inspector = inspect(engine)
        assert not (NEW_TABLES & set(inspector.get_table_names()))
        assert not ({c["name"] for c in inspector.get_columns("complaints")} & NEW_COMPLAINT_COLUMNS)
        assert inspector.get_check_constraints("complaints") == []
        assert {fk["name"] for fk in inspector.get_foreign_keys("complaints")} == {
            "fk_complaints_created_by_id_users", "fk_complaints_department_id_departments",
            "fk_complaints_floor_id_hostel_floors",
        }
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar_one() == 6
            assert conn.execute(text("SELECT floor_id FROM complaints WHERE id = 4")).scalar_one() == 1
            assert conn.execute(text("SELECT hostel FROM complaints WHERE id = 3")).scalar_one() == "Block B"

        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_0012
            assert conn.execute(text(
                "SELECT publication_status FROM complaints WHERE id = 4"
            )).scalar_one() == "pending_mapping"
    finally:
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL"),
    reason="Set CCMS_DISPOSABLE_TEST_POSTGRES_URL to a dedicated, empty, local PostgreSQL test database",
)
def test_postgresql_public_feed_migrations_roundtrip():
    from test_migration_0007_complaint_lifecycle import _disposable_postgres_url_problem, _user_tables

    url = os.environ["CCMS_DISPOSABLE_TEST_POSTGRES_URL"]
    problem = _disposable_postgres_url_problem(url)
    if problem:
        pytest.fail(f"Refusing to use CCMS_DISPOSABLE_TEST_POSTGRES_URL: {problem}")
    engine = create_engine(url)
    if _user_tables(engine):
        engine.dispose()
        pytest.fail("Refusing to modify a populated database; CCMS_DISPOSABLE_TEST_POSTGRES_URL must be empty.")

    config = _config(url)
    try:
        # env.py widens alembic_version only once it exists; stop before 0006 first.
        command.upgrade(config, "0005_email_verification_tokens")
        command.upgrade(config, REV_0010)
        _seed_at_0010(engine)
        command.upgrade(config, "head")
        with engine.connect() as conn:
            statuses = conn.execute(text("SELECT id, publication_status FROM complaints ORDER BY id")).all()
            assert [tuple(r) for r in statuses] == [
                (1, "published"), (2, "pending_mapping"), (3, "pending_mapping"),
                (4, "pending_mapping"), (5, "private"), (6, "private"),
            ]
            checks = set(conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'complaints'::regclass AND contype = 'c'"
            )).scalars())
            assert {
                "ck_complaints_visibility_scope", "ck_complaints_feed_review_status",
                "ck_complaints_publication_status", "ck_complaints_public_scope_consistency",
                "ck_complaints_department_public_no_location",
            } <= checks
        with engine.connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("UPDATE complaints SET visibility_scope = 'department_public' WHERE id = 4"))
            conn.rollback()

        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            watched = NEW_TABLES | {"complaint_hmc_audiences", "complaints"}
            diffs = [
                diff for diff in compare_metadata(context, Base.metadata)
                if any(f"'{table}'" in repr(diff) or f"<{table}>" in repr(diff) for table in watched)
            ]
        assert diffs == []

        command.downgrade(config, REV_0010)
        inspector = inspect(engine)
        assert not (NEW_TABLES & set(inspector.get_table_names()))
        assert not ({c["name"] for c in inspector.get_columns("complaints")} & NEW_COMPLAINT_COLUMNS)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar_one() == 6
        command.upgrade(config, "head")
    finally:
        try:
            command.downgrade(config, "base")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        finally:
            engine.dispose()
