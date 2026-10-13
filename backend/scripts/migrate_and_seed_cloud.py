"""
Cloud Database Migration & Setup Automator for CCMS (Supabase / PostgreSQL)

Executes safe setup steps against a target PostgreSQL database:
1. Verifies connectivity to the target database.
2. Applies all Alembic migrations up to head.
3. Idempotently seeds active campus departments.
4. Production safety: Demo accounts are SKIPPED by default.
   Demo account seeding is restricted to development/staging testing.

Usage:
    python scripts/migrate_and_seed_cloud.py --db-url "postgresql+psycopg://postgres:[PWD]@db.[REF].supabase.co:5432/postgres"
    or set DATABASE_URL environment variable and run:
    python scripts/migrate_and_seed_cloud.py
"""

import os
import sys
import argparse
from urllib.parse import urlparse

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command


def mask_db_url(url: str) -> str:
    """Masks database password in connection strings for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":********@")
            return parsed._replace(netloc=netloc).geturl()
    except Exception:
        pass
    if "@" in url and ":" in url.split("@")[0]:
        prefix, rest = url.split("@", 1)
        scheme_user = prefix.split("://")
        if len(scheme_user) == 2 and ":" in scheme_user[1]:
            user = scheme_user[1].split(":")[0]
            return f"{scheme_user[0]}://{user}:********@{rest}"
    return url


def run_cloud_setup(db_url: str, seed_demo: bool = False):
    print("=" * 75)
    print("CCMS CLOUD DATABASE MIGRATION & SEEDING AUTOMATOR")
    print("=" * 75)

    # Standardize driver prefix
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    masked_url = mask_db_url(db_url)
    print(f"\n[Step 1/5] Target Database: {masked_url}")

    os.environ["DATABASE_URL"] = db_url

    # Step 2: Test raw database connection
    print("\n[Step 2/5] Testing PostgreSQL connection...")
    try:
        connect_args = {}
        if ":6543" in db_url or "pooler.supabase.com" in db_url:
            connect_args["prepare_threshold"] = None
        engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
        with engine.connect() as conn:
            res = conn.execute(text("SELECT version();")).scalar()
            print(f"  Connected successfully! Engine: {res.split(',')[0] if res else 'PostgreSQL'}")
    except Exception as e:
        print(f"  Connection failed: {e}")
        print("\nPlease verify:")
        print("  1. Password is correct.")
        print("  2. Hostname and port are reachable.")
        print("  3. Database project is active (not paused).")
        return False

    # Step 3: Run Alembic migrations
    print("\n[Step 3/5] Applying Alembic database migrations (upgrade head)...")
    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        alembic_ini_path = os.path.join(backend_dir, "alembic.ini")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
        alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

        import app.db.session as session_module
        session_module.engine = engine
        session_module.SessionLocal.configure(bind=engine)

        command.upgrade(alembic_cfg, "head")
        print("  All migrations applied cleanly up to head!")
    except Exception as e:
        print(f"  Migration failure: {e}")
        return False

    # Step 4: Seed departments
    print("\n[Step 4/5] Seeding active campus departments (idempotent)...")
    try:
        from app.db.session import SessionLocal
        from app.scripts.seed_departments import seed_departments
        from app.models.department import Department

        db = SessionLocal()
        try:
            seed_departments(db)
            active_depts = db.query(Department).filter(Department.is_active.is_(True)).count()
            print(f"  Department catalog ready ({active_depts} active departments seeded).")
        finally:
            db.close()
    except Exception as e:
        print(f"  Department seeding failure: {e}")
        return False

    # Step 5: Demo accounts (strictly skipped in production by default)
    if seed_demo:
        print("\n[Step 5/5] Seeding demonstration admin and staff accounts (requested)...")
        try:
            from app.db.session import SessionLocal
            from app.scripts.seed_dev_users import seed_development_users
            from app.models.user import User

            db = SessionLocal()
            try:
                os.environ["ALLOW_DEMO_SEEDING"] = "true"
                seed_development_users(db)
                user_count = db.query(User).count()
                print(f"  Demo accounts ready (Total registered users: {user_count}).")
            finally:
                db.close()
        except Exception as e:
            print(f"  User seeding failure: {e}")
            return False
    else:
        print("\n[Step 5/5] Skipping demo account seeding (production default: demo accounts disabled).")

    print("\n" + "=" * 75)
    print("CLOUD DATABASE INITIALIZATION COMPLETE.")
    print("=" * 75)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCMS Cloud Database Setup Automator")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection string")
    parser.add_argument("--seed-demo", action="store_true", help="Explicitly enable seeding demo accounts for test environments")
    parser.add_argument("--no-demo", action="store_true", help="Explicitly skip seeding demo accounts (default)")
    args = parser.parse_args()

    if not args.db_url:
        print("Error: No database URL provided. Pass --db-url or set DATABASE_URL environment variable.")
        sys.exit(1)

    should_seed = args.seed_demo and not args.no_demo
    ok = run_cloud_setup(args.db_url, seed_demo=should_seed)
    sys.exit(0 if ok else 1)
