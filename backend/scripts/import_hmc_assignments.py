"""Dry-run-first import of the verified HMC roster onto the canonical hostel hierarchy.

CSV columns: hostel_code,wing_code,floor_code,hmc_group_name,student_email,moderator_email

One row maps one canonical wing floor to one HMC group; repeat rows for students
or moderators on that mapping. Hostels, wings and floors must already exist and
be active (the canonical hierarchy is the only location source; this script
never creates locations). A group covers one or two wings at one floor level of
one hostel.

--apply requires --verified-by-email for an active administrator; each imported
student residence is recorded in student_residences as verified by that admin.
--stage-legacy-complaints additionally moves legacy text-only pending_mapping
complaints whose text names exactly one canonical floor to pending_review; they
still need moderator approval before any feed shows them.
"""
from __future__ import annotations
import argparse, csv, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.complaint import Complaint
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.services.public_feed_service import valid_hmc_group

REQUIRED = {"hostel_code", "wing_code", "floor_code", "hmc_group_name", "student_email", "moderator_email"}

def clean(value):
    return " ".join((value or "").strip().split())

def code(value):
    return clean(value).upper()

def rows_from_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED.issubset(set(reader.fieldnames)):
            raise ValueError("CSV header must include: " + ",".join(sorted(REQUIRED)))
        rows = []
        for line, raw in enumerate(reader, start=2):
            row = {k: clean(raw.get(k)) for k in REQUIRED}
            if not all(row[k] for k in ("hostel_code", "wing_code", "floor_code", "hmc_group_name")):
                raise ValueError(f"Line {line}: hostel, wing, floor codes and group name are required")
            for key in ("hostel_code", "wing_code", "floor_code"):
                row[key] = code(row[key])
            row["student_email"] = row["student_email"].lower()
            row["moderator_email"] = row["moderator_email"].lower()
            row["line_no"] = line
            rows.append(row)
        if not rows:
            raise ValueError("CSV contains no mapping rows")
        return rows

def validate(rows):
    groups, group_level, location_group, student_location = defaultdict(set), {}, {}, {}
    moderators = defaultdict(set)
    for row in rows:
        loc = (row["hostel_code"], row["wing_code"], row["floor_code"])
        group = row["hmc_group_name"].casefold()
        level = (loc[0], loc[2])
        if group in group_level and group_level[group] != level:
            raise ValueError(f"Line {row['line_no']}: an HMC group must cover one hostel floor level")
        group_level[group] = level
        groups[group].add(loc[1])
        if len(groups[group]) > 2:
            raise ValueError(f"Line {row['line_no']}: HMC group '{row['hmc_group_name']}' has more than two wings")
        if loc in location_group and location_group[loc] != group:
            raise ValueError(f"Line {row['line_no']}: this hostel/wing/floor is mapped to multiple HMC groups")
        location_group[loc] = group
        if row["student_email"]:
            old = student_location.get(row["student_email"])
            if old is not None and old != loc:
                raise ValueError(f"Line {row['line_no']}: student {row['student_email']} has multiple residence locations")
            student_location[row["student_email"]] = loc
        if row["moderator_email"]:
            moderators[group].add(row["moderator_email"])
    return student_location, moderators

def canonical_floor(db: Session, hostel_code: str, wing_code: str, floor_code: str) -> HostelFloor:
    floor = db.query(HostelFloor).join(HostelWing, HostelWing.id == HostelFloor.wing_id).join(
        Hostel, Hostel.id == HostelWing.hostel_id
    ).filter(
        Hostel.code == hostel_code, HostelWing.code == wing_code, HostelFloor.code == floor_code,
        Hostel.is_active.is_(True), HostelWing.is_active.is_(True), HostelFloor.is_active.is_(True),
    ).first()
    if floor is None:
        raise ValueError(f"No active canonical floor {hostel_code}/{wing_code}/{floor_code}; add it to the hostel hierarchy first")
    return floor

def import_rows(db: Session, rows, verified_by: User | None, *, update_student_assignments: bool, replace_hmc_mappings: bool):
    if verified_by is None:
        raise ValueError("--apply requires an active admin in --verified-by-email so imported residences have an auditable verifier")
    student_locations, moderators = validate(rows)
    floors, groups = {}, {}
    created_groups = mappings = assignments = moderator_count = 0
    for row in rows:
        loc = (row["hostel_code"], row["wing_code"], row["floor_code"])
        floor = floors.get(loc) or canonical_floor(db, *loc)
        floors[loc] = floor
        gkey = row["hmc_group_name"].casefold()
        group = groups.get(gkey) or db.query(HMCGroup).filter(func.lower(HMCGroup.name) == gkey).first()
        if group is None:
            group = HMCGroup(name=row["hmc_group_name"], hostel_id=floor.wing.hostel_id, floor_code=floor.code)
            db.add(group); db.flush(); created_groups += 1
        elif group.hostel_id != floor.wing.hostel_id or group.floor_code != floor.code:
            raise ValueError(f"Existing HMC group {group.name!r} covers a different hostel floor level")
        groups[gkey] = group
        existing = db.query(HMCGroupFloor).filter(HMCGroupFloor.floor_id == floor.id).first()
        if existing and existing.hmc_group_id != group.id:
            if not replace_hmc_mappings:
                raise ValueError(f"Floor {'/'.join(loc)} belongs to a different group; use --replace-hmc-mappings only after verifying the full CSV")
            db.delete(existing); db.flush(); existing = None
        if existing is None:
            db.add(HMCGroupFloor(hmc_group_id=group.id, floor_id=floor.id)); db.flush(); mappings += 1

    for group in groups.values():
        db.refresh(group)
        if not valid_hmc_group(db, group):
            raise ValueError(f"HMC group {group.name!r} would not be valid (1-2 active wings, one hostel floor level)")

    now = datetime.now(timezone.utc)
    for email, loc in student_locations.items():
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is None or user.role != "student" or not user.is_active:
            raise ValueError(f"Student account {email!r} does not exist, is inactive, or is not a student")
        floor = floors[loc]
        residence = db.query(StudentResidence).filter(StudentResidence.student_id == user.id).first()
        if residence is not None and residence.floor_id != floor.id and not update_student_assignments:
            raise ValueError(f"Student {email!r} already has a different residence; use --update-student-assignments after verification")
        if residence is None:
            residence = StudentResidence(student_id=user.id, floor_id=floor.id)
            db.add(residence)
        residence.floor_id = floor.id
        residence.status = "verified"
        residence.remark = None
        residence.verified_by_id = verified_by.id
        residence.verified_at = now
        assignments += 1

    for group_key, emails in moderators.items():
        group = groups[group_key]
        for email in emails:
            user = db.query(User).filter(func.lower(User.email) == email).first()
            if user is None or user.role != "staff" or not user.is_active:
                raise ValueError(f"Moderator {email!r} must be an active staff account")
            existing = db.query(HMCGroupModerator).filter(HMCGroupModerator.hmc_group_id == group.id,
                HMCGroupModerator.user_id == user.id).first()
            if existing is None:
                db.add(HMCGroupModerator(hmc_group_id=group.id, user_id=user.id, assigned_by_user_id=verified_by.id))
                moderator_count += 1
    db.flush()
    return created_groups, mappings, assignments, moderator_count

def _named_floor(db: Session, hostel: str, wing: str, floor: str) -> HostelFloor | None:
    """The single active floor whose hostel, wing and floor each match by exact name or code."""
    def matches(model, value):
        value = clean(value).casefold()
        return (func.lower(model.name) == value) | (func.lower(model.code) == value)
    found = db.query(HostelFloor).join(HostelWing, HostelWing.id == HostelFloor.wing_id).join(
        Hostel, Hostel.id == HostelWing.hostel_id
    ).filter(
        matches(Hostel, hostel), matches(HostelWing, wing), matches(HostelFloor, floor),
        Hostel.is_active.is_(True), HostelWing.is_active.is_(True), HostelFloor.is_active.is_(True),
    ).all()
    return found[0] if len(found) == 1 else None

def stage_legacy_complaints(db: Session) -> int:
    """Attach an unambiguous canonical floor to legacy text locations and queue them for review."""
    staged = 0
    legacy = db.query(Complaint).filter(Complaint.is_public.is_(True), Complaint.floor_id.is_(None),
        Complaint.publication_status == "pending_mapping").all()
    for complaint in legacy:
        if not (clean(complaint.hostel) and clean(complaint.wing) and clean(complaint.floor)):
            continue
        floor = _named_floor(db, complaint.hostel, complaint.wing, complaint.floor)
        if floor is None:
            continue
        complaint.floor_id = floor.id  # original text columns are kept
        complaint.visibility_scope = "hmc_group_public"
        complaint.feed_review_status = "pending"
        complaint.publication_status = "pending_review"
        staged += 1
    return staged

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is a dry run")
    parser.add_argument("--verified-by-email", help="Active administrator email recorded as verifier")
    parser.add_argument("--update-student-assignments", action="store_true")
    parser.add_argument("--replace-hmc-mappings", action="store_true")
    parser.add_argument("--stage-legacy-complaints", action="store_true",
                        help="Queue unambiguous legacy text locations for moderator review")
    args = parser.parse_args()
    if not args.csv_path.is_file(): parser.error(f"CSV not found: {args.csv_path}")
    rows = rows_from_csv(args.csv_path)
    validate(rows)
    db = SessionLocal()
    try:
        verifier = None
        if args.verified_by_email:
            verifier = db.query(User).filter(func.lower(User.email) == args.verified_by_email.lower(),
                User.role == "admin", User.is_active.is_(True)).first()
            if verifier is None: raise ValueError("--verified-by-email must identify an active administrator")
        result = import_rows(db, rows, verifier, update_student_assignments=args.update_student_assignments,
            replace_hmc_mappings=args.replace_hmc_mappings)
        labels = ("HMC groups created", "floor mappings added", "student residences verified", "moderators added")
        for label, count in zip(labels, result): print(f"{label}: {count}")
        if args.stage_legacy_complaints:
            print(f"legacy complaints staged for review: {stage_legacy_complaints(db)}")
        if args.apply:
            db.commit(); print("Import committed.")
        else:
            db.rollback(); print("DRY RUN ONLY - no changes committed. Re-run with --apply after verifying the official roster.")
    except Exception as exc:
        db.rollback(); print(f"Import aborted: {exc}", file=sys.stderr); return 2
    finally:
        db.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
