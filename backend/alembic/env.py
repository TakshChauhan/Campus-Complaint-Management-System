import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, engine_from_config, inspect, pool, text
from alembic import context

# Ensure backend root is on Python sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL dynamically from app settings if not provided
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

# Model metadata for autogenerate support
target_metadata = Base.metadata


def reconcile_alembic_version_compatibility(connection) -> None:
    """
    Migration Compatibility Strategy:
    1. Deliberately widens alembic_version.version_num to VARCHAR(64) on PostgreSQL
       so historical or future revisions exceeding 32 characters do not fail.
    2. Seamlessly reconciles legacy 33-character revision identifier
       '0002_history_index_and_role_check' to canonical '0002_history_idx_role_check'
       without rerunning existing schema changes or requiring manual database stamps.
    """
    inspector = inspect(connection)
    if "alembic_version" in inspector.get_table_names():
        dialect_name = connection.dialect.name
        # 1. Deliberate version-column widening for PostgreSQL
        if dialect_name == "postgresql":
            try:
                connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);"))
                connection.commit()
            except Exception:
                pass

        # 2. Check recorded version in alembic_version table
        try:
            res = connection.execute(text("SELECT version_num FROM alembic_version;")).fetchall()
            recorded_versions = [row[0] for row in res]
            # Contributor branch used a different revision ID for the same FK-hardening
            # migration. Normalize ONLY when the existing live FK already enforces
            # RESTRICT/NO ACTION, so schema history is never falsely marked applied.
            if "0004_restrict_complaint_delete" in recorded_versions:
                fk_list = inspect(connection).get_foreign_keys("complaints")
                creator_fk = next((fk for fk in fk_list
                                   if fk.get("referred_table") == "users"
                                   and fk.get("constrained_columns") == ["created_by_id"]), None)
                delete_behavior = str((creator_fk or {}).get("options", {}).get("ondelete", "")).upper()
                if creator_fk is None or delete_behavior not in ("RESTRICT", "NO ACTION"):
                    raise RuntimeError(
                        "Cannot reconcile migration 0004: existing complaints FK does not enforce RESTRICT. "
                        "Inspect the database before running migrations."
                    )
                connection.execute(text(
                    "UPDATE alembic_version SET version_num = '0004_complaint_fk_restrict' "
                    "WHERE version_num = '0004_restrict_complaint_delete'"
                ))
                connection.commit()
            if "0002_history_index_and_role_check" in recorded_versions:
                connection.execute(
                    text(
                        "UPDATE alembic_version "
                        "SET version_num = '0002_history_idx_role_check' "
                        "WHERE version_num = '0002_history_index_and_role_check';"
                    )
                )
                connection.commit()
        except RuntimeError:
            raise
        except Exception:
            pass


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        url = url.replace("%%", "%")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    target_url = config.get_main_option("sqlalchemy.url")
    if target_url:
        target_url = target_url.replace("%%", "%")
        connectable = create_engine(target_url, poolclass=pool.NullPool)
    else:
        from app.db.session import engine
        connectable = engine

    with connectable.connect() as connection:
        reconcile_alembic_version_compatibility(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
