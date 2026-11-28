"""Seed the throwaway end-to-end database (S5-35).

Run from ``backend/`` against a disposable SQLite file, never a shared database:

    DATABASE_URL=sqlite:///./e2e.db PYTHONPATH=. .venv/bin/python ../e2e/seed_e2e.py

Creates one hostel (wing + floor), five accounts and two complaints that the
GUI tests in ``e2e/tests`` rely on. All accounts use the test-only password
below (E2E_PASSWORD overrides it); none of these accounts exist anywhere else.
"""

import os
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.complaint import Complaint
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User

TEST_PASSWORD = os.getenv("E2E_PASSWORD", "E2e-Only-Passw0rd!")

ACCOUNTS = {
    "student": ("E2E Student", "e2e.student@dau.ac.in", "student", None),
    "it_staff": ("E2E IT Staff", "e2e.it.staff@dau.ac.in", "staff", "IT Services"),
    "warden": ("E2E Warden", "e2e.warden@dau.ac.in", "staff", "Hostel"),
    "new_warden": ("E2E New Warden", "e2e.new.warden@dau.ac.in", "staff", "Hostel"),
    "admin": ("E2E Admin", "e2e.admin@dau.ac.in", "admin", None),
}

# Text the tests type to trigger the duplicate warning (see raise-complaint.spec.ts).
OPEN_TITLE = "Projector not working in lab 3"
OPEN_DESCRIPTION = "The projector in computer lab 3 shows no signal from any laptop since Monday."
RESOLVED_TITLE = "Wi-Fi drops in library reading room"
RESOLVED_DESCRIPTION = "The library reading room Wi-Fi disconnects every few minutes during the day."


def main() -> None:
    if not settings.DATABASE_URL.startswith("sqlite") or "e2e" not in settings.DATABASE_URL:
        sys.exit("Refusing to seed: DATABASE_URL must be the disposable e2e SQLite file.")

    db = SessionLocal()
    try:
        departments = {d.name: d for d in db.query(Department).all()}
        missing = {"IT Services", "Hostel"} - departments.keys()
        if missing:
            sys.exit(f"Run app.scripts.seed_departments first; missing: {sorted(missing)}")

        hostel = Hostel(code="E2E", name="E2E Hostel", is_active=True)
        db.add(hostel)
        db.flush()
        wing = HostelWing(hostel_id=hostel.id, code="A", name="Wing A", is_active=True)
        db.add(wing)
        db.flush()
        floor = HostelFloor(wing_id=wing.id, code="1", name="Floor 1", is_active=True)
        db.add(floor)
        db.flush()

        now = datetime.now(timezone.utc)
        users = {}
        for key, (name, email, role, department) in ACCOUNTS.items():
            user = User(
                name=name,
                email=email,
                role=role,
                password_hash=get_password_hash(TEST_PASSWORD),
                is_active=True,
                email_verified=True,
                email_verified_at=now,
                department_id=departments[department].id if department else None,
            )
            db.add(user)
            users[key] = user
        db.flush()

        db.add(
            StaffHostelAssignment(
                user_id=users["warden"].id, hostel_id=hostel.id, assigned_by_id=users["admin"].id
            )
        )

        it = departments["IT Services"]
        db.add_all(
            [
                Complaint(
                    title=OPEN_TITLE,
                    description=OPEN_DESCRIPTION,
                    department_id=it.id,
                    created_by_id=users["student"].id,
                    status="submitted",
                ),
                Complaint(
                    title=RESOLVED_TITLE,
                    description=RESOLVED_DESCRIPTION,
                    department_id=it.id,
                    created_by_id=users["student"].id,
                    status="resolved",
                    resolved_at=now,
                ),
            ]
        )
        db.commit()
        print(f"Seeded e2e data: {len(users)} accounts, 1 hostel, 2 complaints.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
