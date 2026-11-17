import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(db_url: str) -> Config:
    cfg = Config(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic")))
    return cfg


def _columns(inspector, table_name: str) -> dict:
    return {column["name"]: column for column in inspector.get_columns(table_name)}


def _foreign_keys(inspector, table_name: str) -> dict:
    return {fk["constrained_columns"][0]: fk for fk in inspector.get_foreign_keys(table_name)}


def _check_names(inspector, table_name: str) -> set[str]:
    return {check["name"] for check in inspector.get_check_constraints(table_name)}


def _checks(inspector, table_name: str) -> dict:
    return {check["name"]: check["sqltext"] for check in inspector.get_check_constraints(table_name)}


def test_sprint5_migrations_create_expected_schema_and_cycle(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'sprint5_migrations.db'}"
    cfg = _config(db_url)
    engine = create_engine(db_url)

    command.upgrade(cfg, "head")
    inspector = inspect(engine)

    assert {"complaint_comments", "complaint_feedback", "password_reset_tokens"}.issubset(
        inspector.get_table_names()
    )

    comment_columns = _columns(inspector, "complaint_comments")
    assert set(comment_columns) == {"id", "complaint_id", "author_id", "body", "created_at"}
    assert comment_columns["id"]["nullable"] is False
    assert comment_columns["complaint_id"]["nullable"] is False
    assert comment_columns["author_id"]["nullable"] is False
    assert comment_columns["body"]["nullable"] is False
    assert comment_columns["created_at"]["nullable"] is False
    comment_fks = _foreign_keys(inspector, "complaint_comments")
    assert comment_fks["complaint_id"]["referred_table"] == "complaints"
    assert comment_fks["complaint_id"]["referred_columns"] == ["id"]
    assert comment_fks["complaint_id"]["options"]["ondelete"] == "RESTRICT"
    assert comment_fks["author_id"]["referred_table"] == "users"
    assert comment_fks["author_id"]["referred_columns"] == ["id"]
    assert comment_fks["author_id"]["options"]["ondelete"] == "RESTRICT"
    assert "length(body) BETWEEN 1 AND 1000" in _checks(inspector, "complaint_comments")[
        "ck_complaint_comments_body_length"
    ].replace("(", "").replace(")", "")
    assert "ix_complaint_comments_complaint_created_id" in {
        index["name"] for index in inspector.get_indexes("complaint_comments")
    }

    feedback_columns = _columns(inspector, "complaint_feedback")
    assert set(feedback_columns) == {"id", "complaint_id", "student_id", "rating", "comment", "created_at"}
    assert feedback_columns["complaint_id"]["nullable"] is False
    assert feedback_columns["student_id"]["nullable"] is False
    assert feedback_columns["rating"]["nullable"] is False
    assert feedback_columns["comment"]["nullable"] is True
    feedback_fks = _foreign_keys(inspector, "complaint_feedback")
    assert feedback_fks["complaint_id"]["referred_table"] == "complaints"
    assert feedback_fks["complaint_id"]["options"]["ondelete"] == "RESTRICT"
    assert feedback_fks["student_id"]["referred_table"] == "users"
    assert feedback_fks["student_id"]["options"]["ondelete"] == "RESTRICT"
    assert _check_names(inspector, "complaint_feedback") == {
        "ck_complaint_feedback_rating",
        "ck_complaint_feedback_comment_length",
    }
    feedback_checks = _checks(inspector, "complaint_feedback")
    assert "rating BETWEEN 1 AND 5" in feedback_checks["ck_complaint_feedback_rating"]
    assert "comment IS NULL OR length(comment) <= 500" in feedback_checks[
        "ck_complaint_feedback_comment_length"
    ].replace("(", "").replace(")", "")
    assert "uq_complaint_feedback_complaint_id" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("complaint_feedback")
    }

    reset_columns = _columns(inspector, "password_reset_tokens")
    assert set(reset_columns) == {"id", "user_id", "token_hash", "expires_at", "used_at", "created_at"}
    assert reset_columns["user_id"]["nullable"] is False
    assert reset_columns["token_hash"]["nullable"] is False
    assert reset_columns["expires_at"]["nullable"] is False
    assert reset_columns["used_at"]["nullable"] is True
    reset_fks = _foreign_keys(inspector, "password_reset_tokens")
    assert reset_fks["user_id"]["referred_table"] == "users"
    assert reset_fks["user_id"]["referred_columns"] == ["id"]
    assert reset_fks["user_id"]["options"]["ondelete"] == "CASCADE"
    assert "uq_password_reset_tokens_token_hash" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("password_reset_tokens")
    }
    assert "ix_password_reset_tokens_token_hash" in {
        index["name"] for index in inspector.get_indexes("password_reset_tokens")
    }
    assert {
        "ix_password_reset_tokens_id",
        "ix_password_reset_tokens_user_id",
        "ix_password_reset_tokens_token_hash",
        "ix_password_reset_tokens_expires_at",
    }.issubset({index["name"] for index in inspector.get_indexes("password_reset_tokens")})

    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0017_password_reset_tokens"

    command.downgrade(cfg, "0014_staff_hostel_assignments")
    tables = set(inspect(engine).get_table_names())
    assert not {"complaint_comments", "complaint_feedback", "password_reset_tokens"} & tables

    command.upgrade(cfg, "head")
    assert {"complaint_comments", "complaint_feedback", "password_reset_tokens"}.issubset(
        inspect(engine).get_table_names()
    )
