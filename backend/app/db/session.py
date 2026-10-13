from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

# Engine configuration supporting PostgreSQL (dev/prod/Supabase) and SQLite (tests/local)
connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,
}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # Explicit bounded connection pool configuration for PostgreSQL/cloud/Supabase
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
    engine_kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
    engine_kwargs["pool_recycle"] = settings.DB_POOL_RECYCLE

    # Supabase Transaction Pooler (Supavisor / PgBouncer port 6543) compatibility:
    # Disable prepared statements in transaction mode to prevent 'prepared statement does not exist' errors
    if ":6543" in settings.DATABASE_URL or "pooler.supabase.com" in settings.DATABASE_URL:
        connect_args["prepare_threshold"] = None

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

# Enforce foreign key constraints on SQLite connections (matches PostgreSQL semantics)
@event.listens_for(engine, "connect")
def _set_sqlite_foreign_keys(dbapi_connection, connection_record):
    if type(dbapi_connection).__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency to provide a transactional SQLAlchemy session per request.
    Ensures safe rollback on exception and cleanly closed connections."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
