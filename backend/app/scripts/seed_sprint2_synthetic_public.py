"""Optional, SYNTHETIC public complaints for the Sprint 2 demo.

The 22 student-sourced complaints from seed_sprint2_demo stay private and
"submitted". This optional fixture adds clearly synthetic public complaints
(sprint2_synthetic_public_complaints.json) with valid status histories so the
campus feed, history timeline, reopen flow and admin resolution metrics have
something to show on a local database.

Rules followed by the fixture:
- Only the Sprint 2 transitions are used: submitted -> in_progress -> resolved,
  resolved -> reopened -> in_progress.
- Staff of the complaint's department perform staff transitions; the owner
  (the synthetic author) performs reopens.
- Timestamps are anchored to the time of the first run, so resolved complaints
  fall inside a 30-day rolling-average window.
- resolved_at is the most recent resolution while the status is "resolved",
  and NULL otherwise; reopen_count counts "reopened" events. Adjust if the
  services adopt a different rule.

Run after seed_departments and seed_sprint2_demo (it needs their staff):
    python -m app.scripts.seed_sprint2_synthetic_public
Restricted to a development/testing SQLite database. Safe to run repeatedly.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.seed_sprint2_synthetic_public")

DATA_FILE = Path(__file__).with_name("sprint2_synthetic_public_complaints.json")
SYNTHETIC_REMARK = "Synthetic demonstration data"
ALLOWED_TRANSITIONS = {
    ("submitted", "in_progress"),
    ("in_progress", "resolved"),
    ("resolved", "reopened"),
    ("reopened", "in_progress"),
}


def _require_local_sqlite(db: Session) -> None:
    if settings.ENVIRONMENT not in {"development", "testing"} or not settings.DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Synthetic demo seeding requires a development/testing SQLite database")
    if db.get_bind().dialect.name != "sqlite":
        raise RuntimeError("Synthetic demo seeding requires a development/testing SQLite database")


def load_fixture() -> dict:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    titles = set()
    for record in data["complaints"]:
        title = record["title"].strip()
        if not title or len(title) > 120 or not record["description"].strip():
            raise RuntimeError(f"Invalid synthetic complaint text: {title!r}")
        if title in titles:
            raise RuntimeError(f"Duplicate synthetic complaint title: {title}")
        titles.add(title)
        for field, max_length in (("hostel", 100), ("wing", 50), ("floor", 20)):
            value = record.get(field)
            if value is not None and (not value.strip() or len(value) > max_length):
                raise RuntimeError(f"Invalid synthetic complaint {field}: {title}")
        current = "submitted"
        total_hours = 0
        for event in record["events"]:
            if (current, event["to"]) not in ALLOWED_TRANSITIONS:
                raise RuntimeError(f"Invalid transition {current} -> {event['to']}: {title}")
            if event["after_hours"] <= 0:
                raise RuntimeError(f"Events must move forward in time: {title}")
            total_hours += event["after_hours"]
            current = event["to"]
        if total_hours >= record["submitted_days_ago"] * 24:
            raise RuntimeError(f"Synthetic complaint history ends in the future: {title}")
    return data


def _department_staff(db: Session, department: Department) -> User:
    staff = (
        db.query(User)
        .filter(User.role == "staff", User.department_id == department.id, User.is_active.is_(True))
        .order_by(User.id)
        .first()
    )
    if staff is None:
        raise RuntimeError(f"No active staff for {department.name}. Run seed_sprint2_demo first.")
    return staff


def seed_sprint2_synthetic_public(db: Session) -> int:
    """Create the synthetic public complaints that do not exist yet; return how many were created."""
    _require_local_sqlite(db)
    data = load_fixture()

    departments = {dept.name: dept for dept in db.query(Department).all()}
    missing = {record["department"] for record in data["complaints"]} - departments.keys()
    if missing:
        raise RuntimeError(f"Missing departments: {', '.join(sorted(missing))}. Run seed_departments first.")

    author_email = data["author"]["email"].strip().lower()
    author = db.query(User).filter(User.email == author_email).first()
    if author is None:
        # No password: this account owns the synthetic records and cannot log in.
        author = User(
            name=data["author"]["name"],
            email=author_email,
            password_hash=None,
            role="student",
            is_active=True,
            email_verified=False,
            email_verification_required=False,
        )
        db.add(author)
        db.flush()
    elif author.role != "student":
        raise RuntimeError(f"Synthetic author email belongs to a non-student account: {author_email}")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created = 0
    for record in data["complaints"]:
        title = record["title"].strip()
        exists = (
            db.query(Complaint.id)
            .filter(Complaint.created_by_id == author.id, Complaint.title == title)
            .first()
        )
        if exists:
            continue

        department = departments[record["department"]]
        staff = _department_staff(db, department)
        submitted_at = now - timedelta(days=record["submitted_days_ago"])

        history = [
            ComplaintStatusHistory(
                from_status=None,
                to_status="submitted",
                actor_id=author.id,
                remark=SYNTHETIC_REMARK,
                created_at=submitted_at,
            )
        ]
        status, at, resolved_at, reopen_count = "submitted", submitted_at, None, 0
        for event in record["events"]:
            at = at + timedelta(hours=event["after_hours"])
            actor = author if event["to"] == "reopened" else staff
            history.append(
                ComplaintStatusHistory(
                    from_status=status,
                    to_status=event["to"],
                    actor_id=actor.id,
                    remark=event.get("remark"),
                    created_at=at,
                )
            )
            status = event["to"]
            if status == "resolved":
                resolved_at = at
            elif status == "reopened":
                reopen_count += 1

        complaint = Complaint(
            title=title,
            description=record["description"].strip(),
            department_id=department.id,
            created_by_id=author.id,
            status=status,
            is_public=True,
            visibility_scope=("hmc_group_public" if any(record.get(field) for field in ("hostel", "wing", "floor")) else "department_public"),
            feed_review_status=("pending" if any(record.get(field) for field in ("hostel", "wing", "floor")) else "not_required"),
            publication_status=("pending_mapping" if any(record.get(field) for field in ("hostel", "wing", "floor")) else "published"),
            hostel=record.get("hostel"),
            wing=record.get("wing"),
            floor=record.get("floor"),
            created_at=submitted_at,
            updated_at=at,
            resolved_at=resolved_at if status == "resolved" else None,
            reopen_count=reopen_count,
        )
        db.add(complaint)
        db.flush()
        for entry in history:
            entry.complaint_id = complaint.id
            db.add(entry)
        created += 1

    db.commit()
    logger.info("Synthetic Sprint 2 demo seed complete: %d public complaints created", created)
    return created


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_sprint2_synthetic_public(db)
    except Exception:
        db.rollback()
        logger.exception("Synthetic Sprint 2 demo seeding failed")
        sys.exit(1)
    finally:
        db.close()
