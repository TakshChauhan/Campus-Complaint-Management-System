"""Local Sprint 2 demo data: one staff member per department and 22 complaints.

The complaint examples live in sprint2_demo_complaints.json. This script is
restricted to a development/testing SQLite database and may be run repeatedly.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.seed_sprint2_demo")

DATA_FILE = Path(__file__).with_name("sprint2_demo_complaints.json")


def _staff_email(department_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", department_name.lower()).strip(".")
    return f"demo.staff.{slug}@dau.ac.in"


def _load_complaints() -> list[dict]:
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if len(records) != 22:
        raise RuntimeError(f"Expected 22 demo complaints, found {len(records)}")
    for record in records:
        if not all(record.get(field) for field in ("department", "title", "description")):
            raise RuntimeError("Every demo complaint needs a department, title, and description")
        if len(record["title"].strip()) > 120:
            raise RuntimeError(f"Demo complaint title exceeds 120 characters: {record['title']}")
        for field, max_length in (("hostel", 100), ("wing", 50), ("floor", 20)):
            value = record.get(field)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
                    raise RuntimeError(f"Invalid demo complaint {field}: {record['title']}")
                record[field] = value.strip()
    return records


def seed_sprint2_demo(db: Session) -> None:
    # Fail before reading or writing the database if this is not a local demo.
    if settings.ENVIRONMENT not in {"development", "testing"} or not settings.DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Sprint 2 demo seeding requires a development/testing SQLite database")

    records = _load_complaints()
    department_names = {record["department"] for record in records}
    departments = {dept.name: dept for dept in db.query(Department).all()}
    missing = department_names - departments.keys()
    if missing:
        raise RuntimeError(f"Missing departments: {', '.join(sorted(missing))}. Run seed_departments first.")
    if not departments:
        raise RuntimeError("No departments found. Run seed_departments first.")

    staff_created = 0
    for department in departments.values():
        staff = (
            db.query(User)
            .filter(User.role == "staff", User.department_id == department.id, User.is_active.is_(True))
            .first()
        )
        if staff:
            continue
        email = _staff_email(department.name)
        if db.query(User).filter(User.email == email).first():
            raise RuntimeError(f"Demo staff email already belongs to another account: {email}")
        db.add(
            User(
                name=f"Demo {department.name} Staff",
                email=email,
                password_hash=get_password_hash(settings.DEV_STAFF_PASSWORD),
                role="staff",
                department_id=department.id,
                is_active=True,
                email_verified=True,
                email_verification_required=False,
            )
        )
        staff_created += 1

    student_email = os.getenv("DEV_STUDENT_EMAIL", "student@dau.ac.in").strip().lower()
    student = db.query(User).filter(User.email == student_email).first()
    if student is None:
        student = User(
            name="Demo Student",
            email=student_email,
            password_hash=get_password_hash(os.environ["DEV_STUDENT_PASSWORD"]),
            role="student",
            is_active=True,
            email_verified=True,
            email_verification_required=False,
        )
        db.add(student)
        db.flush()
    elif student.role != "student" or not student.is_active:
        raise RuntimeError(f"Demo student email is not an active student account: {student_email}")

    complaints_created = 0
    for record in records:
        title = record["title"].strip()
        description = record["description"].strip()
        location = (record.get("location") or "").strip()
        if location:
            description = f"{description}\n\nLocation: {location}"
        existing = (
            db.query(Complaint)
            .filter(
                Complaint.created_by_id == student.id,
                Complaint.title == title,
                Complaint.description == description,
            )
            .first()
        )
        if existing:
            # Fill structured locations added after an earlier demo seed run.
            for field in ("hostel", "wing", "floor"):
                value = record.get(field)
                if value is not None and getattr(existing, field) is None:
                    setattr(existing, field, value)
            continue

        complaint = Complaint(
            title=title,
            description=description,
            department_id=departments[record["department"]].id,
            created_by_id=student.id,
            status="submitted",
            is_public=False,
            hostel=record.get("hostel"),
            wing=record.get("wing"),
            floor=record.get("floor"),
            reopen_count=0,
        )
        db.add(complaint)
        db.flush()
        db.add(
            ComplaintStatusHistory(
                complaint_id=complaint.id,
                from_status=None,
                to_status="submitted",
                actor_id=student.id,
                remark=None,
            )
        )
        complaints_created += 1

    db.commit()
    logger.info(
        "Sprint 2 demo seed complete: %d staff and %d complaints created",
        staff_created,
        complaints_created,
    )


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_sprint2_demo(db)
    except Exception:
        db.rollback()
        logger.exception("Sprint 2 demo seeding failed")
        sys.exit(1)
    finally:
        db.close()
