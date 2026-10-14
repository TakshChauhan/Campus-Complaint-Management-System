"""
Development-Only Staff & Admin Seeding Script

CRITICAL SECURITY NOTICE:
This script is intended strictly for local development and test environments.
It creates provisional staff and administrator accounts for role verification.
Never run this script in production with default credentials.
Configure custom credentials via environment variables:
  DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
  DEV_STAFF_EMAIL, DEV_STAFF_PASSWORD
"""

import os
import sys
import logging
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.department import Department
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.seed_dev_users")


def seed_development_users(db: Session) -> None:
    from app.core.config import settings

    allow_seeding = (
        settings.ENVIRONMENT in ["development", "testing"]
        or getattr(settings, "ALLOW_DEMO_SEEDING", False)
        or os.getenv("ALLOW_DEMO_SEEDING", "").lower() in ["true", "1", "yes"]
    )
    if not allow_seeding:
        logger.error(
            "Refusing to seed demonstration users: current environment is '%s'. "
            "To permit safe demo-account creation in hosted environments, set ALLOW_DEMO_SEEDING=true.",
            settings.ENVIRONMENT
        )
        raise RuntimeError(f"Demo user seeding forbidden in environment '{settings.ENVIRONMENT}' without ALLOW_DEMO_SEEDING=true")

    logger.info("Checking and seeding demonstration staff/admin accounts in '%s' environment...", settings.ENVIRONMENT)

    admin_email = settings.DEV_ADMIN_EMAIL.strip().lower()
    admin_password = settings.DEV_ADMIN_PASSWORD

    staff_email = settings.DEV_STAFF_EMAIL.strip().lower()
    staff_password = settings.DEV_STAFF_PASSWORD

    # Find required provisional department for staff assignment (IT Services)
    it_dept = db.query(Department).filter(Department.name == "IT Services").first()
    if not it_dept:
        logger.error(
            "Required department 'IT Services' was not found in database. "
            "Please run 'python -m app.scripts.seed_departments' first before running dev user seeding."
        )
        raise RuntimeError("Department 'IT Services' missing. Run python -m app.scripts.seed_departments first.")
    it_dept_id = it_dept.id

    # Seed Admin
    existing_admin = db.query(User).filter(User.email == admin_email).first()
    if not existing_admin:
        admin_user = User(
            name="Campus Administrator",
            email=admin_email,
            password_hash=get_password_hash(admin_password),
            role="admin",
            is_active=True,
        )
        db.add(admin_user)
        logger.info("Created development admin user: %s", admin_email)
    else:
        logger.info("Admin user already exists: %s", admin_email)

    # Seed Staff
    existing_staff = db.query(User).filter(User.email == staff_email).first()
    if not existing_staff:
        staff_user = User(
            name="IT Helpdesk Staff",
            email=staff_email,
            password_hash=get_password_hash(staff_password),
            role="staff",
            is_active=True,
            department_id=it_dept_id,
        )
        db.add(staff_user)
        logger.info("Created development staff user: %s (dept=%s)", staff_email, it_dept_id)
    else:
        logger.info("Staff user already exists: %s", staff_email)

    db.commit()
    logger.info("Development user seeding completed.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_development_users(db)
    except Exception as e:
        logger.error("Error during dev user seeding: %s", str(e))
        db.rollback()
        sys.exit(1)
    finally:
        db.close()
