"""Provision a staff, administrator, or verified demo student account.

Passwords are accepted only through an environment variable or an interactive
prompt.  The command is deliberately idempotent: an existing email is left
unchanged unless ``--update`` is supplied.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User
from app.schemas.auth import RegisterRequest


VALID_ROLES = {"student", "staff", "admin"}


def _get_password() -> str:
    password = os.getenv("CCMS_NEW_USER_PASSWORD")
    if password is None:
        password = getpass.getpass("New user password: ")
    if not password:
        raise ValueError("Password must not be empty")
    return password


def _department(db: Session, name: str | None, role: str) -> Department | None:
    if role != "staff":
        if name:
            raise ValueError("--department is only valid for staff users")
        return None
    if not name or not name.strip():
        raise ValueError("--department is required for staff users")
    department = (
        db.query(Department)
        .filter(Department.name == name.strip(), Department.is_active.is_(True))
        .one_or_none()
    )
    if department is None:
        raise ValueError(f"Active department not found: {name}")
    return department


def _hostels(db: Session, hostel_ids: list[int], department: Department | None) -> list[Hostel]:
    if not hostel_ids:
        return []
    if department is None or department.name.strip().casefold() != "hostel":
        raise ValueError("Hostel assignments are allowed only for Hostel-department staff")
    unique_ids = list(dict.fromkeys(hostel_ids))
    hostels = (
        db.query(Hostel)
        .filter(Hostel.id.in_(unique_ids), Hostel.is_active.is_(True))
        .all()
    )
    found = {hostel.id for hostel in hostels}
    missing = [str(hostel_id) for hostel_id in unique_ids if hostel_id not in found]
    if missing:
        raise ValueError(f"Active hostel(s) not found: {', '.join(missing)}")
    return sorted(hostels, key=lambda hostel: hostel.id)


def provision_user(
    db: Session,
    *,
    email: str,
    name: str,
    role: str,
    department_name: str | None = None,
    hostel_ids: list[int] | None = None,
    assigned_by_email: str | None = None,
    password: str,
    update: bool = False,
) -> tuple[User, str]:
    """Create or optionally update one verified user; return ``(user, action)``."""
    email = email.strip().lower()
    name = name.strip()
    role = role.strip().lower()
    hostel_ids = hostel_ids or []

    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
    # Reuse the web registration rules for email format, allowed domains,
    # name trimming, password whitespace, and the 72-byte bcrypt limit.
    registration = RegisterRequest(name=name, email=email, password=password)
    email = str(registration.email).strip().lower()
    name = registration.name
    password = registration.password
    if role != "staff" and hostel_ids:
        raise ValueError("--hostel is only valid for staff users")
    if assigned_by_email and not hostel_ids:
        raise ValueError("--assigned-by-email requires at least one --hostel")

    department = _department(db, department_name, role)
    hostels = _hostels(db, hostel_ids, department)
    user = db.query(User).filter(User.email == email).one_or_none()

    if user is not None and not update:
        return user, "unchanged"

    now = datetime.now(timezone.utc)
    created = user is None
    if created:
        user = User(email=email)
        db.add(user)

    user.name = name
    user.role = role
    user.password_hash = get_password_hash(password)
    user.is_active = True
    user.email_verified = True
    user.email_verified_at = now
    user.email_verification_required = False
    user.department_id = department.id if department else None
    db.flush()

    db.query(StaffHostelAssignment).filter(
        StaffHostelAssignment.user_id == user.id
    ).delete(synchronize_session=False)
    if role == "staff":
        if hostels and not assigned_by_email:
            raise ValueError("--assigned-by-email is required when assigning hostels")
        assigner = None
        if assigned_by_email:
            assigner = (
                db.query(User)
                .filter(
                    User.email == assigned_by_email.strip().lower(),
                    User.role == "admin",
                    User.is_active.is_(True),
                )
                .one_or_none()
            )
            if assigner is None:
                raise ValueError("Active admin not found for --assigned-by-email")
        db.add_all(
            StaffHostelAssignment(
                user_id=user.id,
                hostel_id=hostel.id,
                assigned_by_id=assigner.id,
            )
            for hostel in hostels
        )

    db.commit()
    db.refresh(user)
    return user, "created" if created else "updated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    parser.add_argument("--department")
    parser.add_argument("--hostel", type=int, action="append", default=[])
    parser.add_argument("--assigned-by-email")
    parser.add_argument("--update", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = SessionLocal()
    try:
        password = _get_password()
        user, action = provision_user(
            db,
            email=args.email,
            name=args.name,
            role=args.role,
            department_name=args.department,
            hostel_ids=args.hostel,
            assigned_by_email=args.assigned_by_email,
            password=password,
            update=args.update,
        )
        print(f"{action.capitalize()}: {user.email} ({user.role})")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
