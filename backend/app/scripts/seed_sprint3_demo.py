"""Local Sprint 3 demo data: DAU hostels, HMC groups, residences and feed complaints.

Locations come from data/dau_hostels.csv. The three building names (OHM "Old
Hostel for Men", NHM "New Hostel for Men", HFW "Hostel for Women") are DAU's
official hostel buildings, but the wing and floor rows are PROVISIONAL until the
HMC confirms them, and the HMC groups built here (one per hostel floor level,
covering its wings) are demo groupings, not the real HMC roster (that is
imported with scripts/import_hmc_assignments.py). Wing codes are globally
unique, so each carries its hostel prefix (OHM-A) while the displayed name is
"Wing A". Demo accounts use generic names; no real names, roll numbers or room
numbers are used.

Residences are set and approved through residence_service and complaints are
created through complaint_service, so verification and publication_status come
from the real rules. This script is restricted to a development/testing SQLite
database and may be run repeatedly.
"""

import csv
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.complaint import Complaint
from app.models.department import Department
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.complaint import ComplaintCreate
from app.schemas.residence import ResidenceDecision
from app.services.complaint_service import create_student_complaint
from app.services.location_service import get_active_hostel_department
from app.services.public_feed_service import valid_hmc_group
from app.services.residence_service import decide_residence, set_my_residence

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.seed_sprint3_demo")

DATA_FILE = Path(__file__).with_name("data") / "dau_hostels.csv"
CSV_COLUMNS = ("hostel_code", "hostel_name", "wing_code", "wing_name", "floor_code", "floor_name")
# Column limits from the Hostel, HostelWing and HostelFloor models.
MAX_LENGTHS = {"hostel_code": 32, "hostel_name": 100, "wing_code": 32, "wing_name": 100,
               "floor_code": 32, "floor_name": 100}
HOSTEL_STAFF_LOCAL_PART = "demo.staff.hostel"  # shared with the Sprint 2 demo seed

# key -> (local part, name, (hostel, wing, floor) codes, verified)
STUDENTS = {
    "h1_student1": ("demo3.h1.student1", "Demo Student 1", ("OHM", "OHM-A", "1"), True),
    "h1_student2": ("demo3.h1.student2", "Demo Student 2", ("OHM", "OHM-A", "1"), True),
    "h2_student": ("demo3.h2.student", "Demo Student 3", ("HFW", "HFW-A", "1"), True),
    "pending_student": ("demo3.pending.student", "Demo Student 4", ("NHM", "NHM-A", "1"), False),
}

COMPLAINTS = [
    {
        "key": "C1", "reporter": "h1_student1", "department": "Hostel", "is_public": True,
        "floor": ("OHM", "OHM-A", "1"), "expected": "published",
        "title": "Water cooler on OHM Wing A first floor not cooling",
        "description": "The water cooler near the stairs on the first floor of OHM Wing A has been giving "
                       "lukewarm water for four days, so students are buying bottled water.",
    },
    {
        "key": "C2", "reporter": "h1_student2", "department": "Hostel", "is_public": False,
        "floor": ("OHM", "OHM-A", "1"), "expected": "private",
        "title": "LAN port in my room has a broken socket",
        "description": "The wall LAN port in my room is cracked and the cable falls out, so I cannot use "
                       "the wired connection for lab assignments.",
    },
    {
        "key": "C3", "reporter": "pending_student", "department": "Hostel", "is_public": True,
        "floor": ("NHM", "NHM-A", "1"), "expected": "pending_review",
        "title": "Laundry machine out of order on NHM Wing A first floor",
        "description": "The washing machine on the first floor of NHM Wing A stops mid-cycle and leaves "
                       "clothes soaked; it has shown an error light since Monday.",
    },
    {
        "key": "C4", "reporter": "h2_student", "department": "Hostel", "is_public": True,
        "floor": ("HFW", "HFW-A", "1"), "expected": "published",
        "title": "Washroom geyser not heating on HFW Wing A first floor",
        "description": "The geyser in the first-floor washroom of HFW Wing A gives only cold water in the "
                       "mornings, which is difficult before early classes.",
    },
    {
        "key": "C5", "reporter": "h1_student1", "department": "IT Services", "is_public": True,
        "floor": None, "expected": "published",
        "title": "Hostel Wi-Fi disconnects every night",
        "description": "Hostel Wi-Fi disconnects every night between 10 pm and 1 am and the login page "
                       "does not load again, so assignment submissions fail.",
    },
    {
        "key": "C6", "reporter": "h1_student2", "department": "Library", "is_public": True,
        "floor": None, "expected": "published",
        "title": "Library reading hall AC not cooling",
        "description": "The air conditioning in the Resource Centre reading hall barely cools in the "
                       "afternoon and the hall gets too warm to study during exams.",
    },
    {
        # Near-duplicate of C5 so the duplicate warning can be demonstrated.
        "key": "C7", "reporter": "h2_student", "department": "IT Services", "is_public": True,
        "floor": None, "expected": "published",
        "title": "Hostel Wi-Fi keeps disconnecting every night",
        "description": "Hostel Wi-Fi disconnects every night between 10 pm and 1 am and the login page "
                       "does not load again, so late assignment submissions fail.",
    },
]

# Which complaints each account should see in /feeds/hostel.
EXPECTED_HOSTEL_FEED = {
    "h1_student1": "C1",
    "h1_student2": "C1",
    "h2_student": "C4",
    "pending_student": "403 residence_not_verified",
    "hostel_staff": "C1, C4",
    "admin": "C1, C4",
}


def _require_local_sqlite(db: Session) -> None:
    # Fail before reading or writing the database if this is not a local demo.
    if settings.ENVIRONMENT not in {"development", "testing"} or not settings.DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Sprint 3 demo seeding requires a development/testing SQLite database")
    # The session may be bound to a different engine than settings.DATABASE_URL.
    if db.get_bind().dialect.name != "sqlite":
        raise RuntimeError("Sprint 3 demo seeding requires a development/testing SQLite database")


def load_locations(path: Path = DATA_FILE) -> list[dict]:
    """Read and validate the hostel/wing/floor rows before anything is written."""
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise RuntimeError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        rows = [{column: " ".join((raw.get(column) or "").split()) for column in CSV_COLUMNS}
                for raw in reader]
    if not rows:
        raise RuntimeError(f"{path.name} contains no location rows")

    seen, hostel_names, wing_owner, wing_names = set(), {}, {}, {}
    level_wings = defaultdict(set)
    for line, row in enumerate(rows, start=2):
        for column, max_length in MAX_LENGTHS.items():
            if not row[column] or len(row[column]) > max_length:
                raise RuntimeError(f"{path.name} line {line}: {column} must be 1-{max_length} characters")
        for column in ("hostel_code", "wing_code", "floor_code"):
            if row[column] != row[column].upper():
                raise RuntimeError(f"{path.name} line {line}: {column} must be upper case")
        key = (row["wing_code"], row["floor_code"])
        if key in seen:
            raise RuntimeError(f"{path.name} line {line}: duplicate wing/floor {'/'.join(key)}")
        seen.add(key)
        if hostel_names.setdefault(row["hostel_code"], row["hostel_name"]) != row["hostel_name"]:
            raise RuntimeError(f"{path.name} line {line}: hostel {row['hostel_code']} has two names")
        if wing_owner.setdefault(row["wing_code"], row["hostel_code"]) != row["hostel_code"]:
            raise RuntimeError(f"{path.name} line {line}: wing {row['wing_code']} is in two hostels")
        if wing_names.setdefault(row["wing_code"], row["wing_name"]) != row["wing_name"]:
            raise RuntimeError(f"{path.name} line {line}: wing {row['wing_code']} has two names")
        level_wings[(row["hostel_code"], row["floor_code"])].add(row["wing_code"])
        if len(level_wings[(row["hostel_code"], row["floor_code"])]) > 2:
            # An HMC group covers at most two wings of one floor level.
            raise RuntimeError(f"{path.name} line {line}: more than two wings on one HMC floor level")
    return rows


def _email(local_part: str) -> str:
    return f"{local_part}@{settings.ALLOWED_EMAIL_DOMAINS[0]}"


def _get_or_create_user(db: Session, email: str, *, name: str, role: str, password: str,
                        department_id: int | None = None) -> tuple[User, bool]:
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        if user.role != role or not user.is_active:
            raise RuntimeError(f"Demo email is not an active {role} account: {email}")
        if department_id is not None and user.department_id != department_id:
            raise RuntimeError(f"Demo staff account belongs to another department: {email}")
        return user, False
    user = User(
        name=name,
        email=email,
        password_hash=get_password_hash(password),
        role=role,
        department_id=department_id,
        is_active=True,
        email_verified=True,
        email_verification_required=False,
    )
    db.add(user)
    db.flush()
    return user, True


def _seed_locations(db: Session, rows: list[dict], created: dict) -> dict:
    hostels, wings, floors = {}, {}, {}
    for row in rows:
        hostel = hostels.get(row["hostel_code"])
        if hostel is None:
            hostel = db.query(Hostel).filter(Hostel.code == row["hostel_code"]).first()
            if hostel is None:
                hostel = Hostel(code=row["hostel_code"], name=row["hostel_name"], is_active=True)
                db.add(hostel)
                db.flush()
                created["hostels"] += 1
            hostels[row["hostel_code"]] = hostel
        wing = wings.get(row["wing_code"])
        if wing is None:
            wing = db.query(HostelWing).filter(HostelWing.code == row["wing_code"]).first()
            if wing is None:
                wing = HostelWing(hostel_id=hostel.id, code=row["wing_code"], name=row["wing_name"], is_active=True)
                db.add(wing)
                db.flush()
                created["wings"] += 1
            elif wing.hostel_id != hostel.id:
                raise RuntimeError(f"Wing {row['wing_code']} belongs to another hostel")
            wings[row["wing_code"]] = wing
        floor = db.query(HostelFloor).filter(
            HostelFloor.wing_id == wing.id, HostelFloor.code == row["floor_code"]
        ).first()
        if floor is None:
            floor = HostelFloor(wing_id=wing.id, code=row["floor_code"], name=row["floor_name"], is_active=True)
            db.add(floor)
            db.flush()
            created["floors"] += 1
        floors[(row["hostel_code"], row["wing_code"], row["floor_code"])] = floor
    return floors


def _seed_hmc_groups(db: Session, rows: list[dict], floors: dict, created: dict) -> list[HMCGroup]:
    # One demo group per hostel floor level, covering that level's wings.
    levels = defaultdict(list)
    for row in rows:
        levels[(row["hostel_code"], row["hostel_name"], row["floor_code"], row["floor_name"])].append(
            floors[(row["hostel_code"], row["wing_code"], row["floor_code"])]
        )
    groups = []
    for (hostel_code, hostel_name, floor_code, floor_name), level_floors in levels.items():
        hostel_id = level_floors[0].wing.hostel_id
        name = f"{hostel_name} {floor_name} HMC"
        group = db.query(HMCGroup).filter(HMCGroup.name == name).first()
        if group is None:
            group = HMCGroup(name=name, hostel_id=hostel_id, floor_code=floor_code, is_active=True)
            db.add(group)
            db.flush()
            created["hmc_groups"] += 1
        elif group.hostel_id != hostel_id or group.floor_code != floor_code:
            raise RuntimeError(f"HMC group {name!r} covers a different hostel floor level")
        for floor in level_floors:
            mapping = db.query(HMCGroupFloor).filter(HMCGroupFloor.floor_id == floor.id).first()
            if mapping is None:
                db.add(HMCGroupFloor(hmc_group_id=group.id, floor_id=floor.id))
                db.flush()
                created["hmc_group_floors"] += 1
            elif mapping.hmc_group_id != group.id:
                raise RuntimeError(
                    f"Floor {hostel_code}/{floor.wing.code}/{floor_code} is mapped to another HMC group"
                )
        groups.append(group)
    for group in groups:
        db.refresh(group)
        if not valid_hmc_group(db, group):
            raise RuntimeError(f"Demo HMC group {group.name!r} is not valid")
    return groups


def _seed_residence(db: Session, student: User, floor: HostelFloor, verified: bool,
                    hostel_staff: User, created: dict) -> None:
    residence = db.query(StudentResidence).filter(StudentResidence.student_id == student.id).first()
    if residence is None or residence.floor_id != floor.id or (verified and residence.status == "rejected"):
        if residence is None:
            created["residences"] += 1
        set_my_residence(db, student, floor.id)
        residence = db.query(StudentResidence).filter(StudentResidence.student_id == student.id).one()
    if verified and residence.status == "pending":
        decide_residence(db, hostel_staff, residence.id, ResidenceDecision(decision="approve"))


def seed_sprint3_demo(db: Session) -> dict:
    _require_local_sqlite(db)
    student_password = os.getenv("DEV_STUDENT_PASSWORD")
    if not student_password:
        raise RuntimeError("Set DEV_STUDENT_PASSWORD before running Sprint 3 demo seeding")

    hostel_department = get_active_hostel_department(db)
    departments = {d.name: d for d in db.query(Department).filter(Department.is_active.is_(True)).all()}
    missing = [name for name in ("IT Services", "Library") if name not in departments]
    if hostel_department is None:
        missing.insert(0, "Hostel")
    if missing:
        raise RuntimeError(f"Missing departments: {', '.join(missing)}. Run seed_departments first.")
    departments["Hostel"] = hostel_department
    rows = load_locations(DATA_FILE)
    known = {(row["hostel_code"], row["wing_code"], row["floor_code"]) for row in rows}
    for location in [student[2] for student in STUDENTS.values()] + [c["floor"] for c in COMPLAINTS if c["floor"]]:
        if location not in known:
            raise RuntimeError(f"Demo location {'/'.join(location)} is not in {DATA_FILE.name}")

    created = dict.fromkeys(
        ("hostels", "wings", "floors", "hmc_groups", "hmc_group_floors", "users", "residences", "complaints"), 0
    )
    floors = _seed_locations(db, rows, created)
    _seed_hmc_groups(db, rows, floors, created)

    accounts = {}
    accounts["admin"], new = _get_or_create_user(
        db, settings.DEV_ADMIN_EMAIL.strip().lower(), name="Campus Administrator", role="admin",
        password=settings.DEV_ADMIN_PASSWORD,
    )
    created["users"] += new
    accounts["hostel_staff"], new = _get_or_create_user(
        db, _email(HOSTEL_STAFF_LOCAL_PART), name="Demo Hostel Staff", role="staff",
        password=settings.DEV_STAFF_PASSWORD, department_id=hostel_department.id,
    )
    created["users"] += new
    for key, (local_part, name, _, _) in STUDENTS.items():
        accounts[key], new = _get_or_create_user(
            db, _email(local_part), name=name, role="student", password=student_password,
        )
        created["users"] += new
    db.commit()

    for key, (_, _, location, verified) in STUDENTS.items():
        _seed_residence(db, accounts[key], floors[location], verified, accounts["hostel_staff"], created)

    statuses, warnings = {}, []
    for record in COMPLAINTS:
        reporter = accounts[record["reporter"]]
        complaint = db.query(Complaint).filter(
            Complaint.created_by_id == reporter.id, Complaint.title == record["title"]
        ).first()
        if complaint is None:
            floor = floors[record["floor"]] if record["floor"] else None
            create_student_complaint(
                db,
                ComplaintCreate(
                    title=record["title"],
                    description=record["description"],
                    department_id=departments[record["department"]].id,
                    is_public=record["is_public"],
                    floor_id=floor.id if floor else None,
                ),
                reporter,
            )
            created["complaints"] += 1
            complaint = db.query(Complaint).filter(
                Complaint.created_by_id == reporter.id, Complaint.title == record["title"]
            ).one()
        statuses[record["key"]] = complaint.publication_status
        if complaint.publication_status != record["expected"]:
            warnings.append(
                f"{record['key']} {record['title']!r} is {complaint.publication_status}, "
                f"expected {record['expected']}"
            )

    _print_summary(accounts, statuses, warnings)
    logger.info("Sprint 3 demo seed complete: %s", ", ".join(f"{v} {k}" for k, v in created.items()))
    return {"created": created, "complaints": statuses, "warnings": warnings}


def _print_summary(accounts: dict, statuses: dict, warnings: list[str]) -> None:
    print("\nSprint 3 demo accounts (passwords come from your environment, never printed):")
    for key, user in accounts.items():
        print(f"  {user.email:<40} {user.role:<8} ({key})")
    print("\nSprint 3 demo complaints:")
    for record in COMPLAINTS:
        floor = "/".join(record["floor"]) if record["floor"] else "no location"
        visibility = "public" if record["is_public"] else "private"
        print(f"  {record['key']} [{record['department']}, {visibility}, {floor}] "
              f"{record['title']} -> {statuses[record['key']]}")
    print("\nExpected /feeds/hostel visibility:")
    for key, visible in EXPECTED_HOSTEL_FEED.items():
        print(f"  {accounts[key].email:<40} {visible}")
    print("Department feeds: IT Services -> C5, C7; Library -> C6. C5 and C7 trigger the duplicate warning.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print()


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_sprint3_demo(db)
    except Exception:
        db.rollback()
        logger.exception("Sprint 3 demo seeding failed")
        sys.exit(1)
    finally:
        db.close()
