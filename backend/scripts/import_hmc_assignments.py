"""Dry-run-first import of the verified building/floor/wing/HMC roster.

CSV columns: building_name,floor_name,wing_name,hmc_group_name,student_email,moderator_email
One row maps one wing to one HMC group on one floor; repeat rows for students or
moderators assigned to that mapping. --apply requires --verified-by-email for an
active administrator; each imported student assignment is then recorded as verified.
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
from app.models.building import Building
from app.models.complaint import Complaint
from app.models.floor import Floor
from app.models.hmc_group import HMCGroup, HMCGroupWing
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.user import User
from app.models.wing import Wing

REQUIRED = {"building_name", "floor_name", "wing_name", "hmc_group_name", "student_email", "moderator_email"}

def clean(value):
    return " ".join((value or "").strip().split())

def rows_from_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED.issubset(set(reader.fieldnames)):
            raise ValueError("CSV header must include: " + ",".join(sorted(REQUIRED)))
        rows = []
        for line, raw in enumerate(reader, start=2):
            row = {k: clean(raw.get(k)) for k in REQUIRED}
            if not all(row[k] for k in ("building_name", "floor_name", "wing_name", "hmc_group_name")):
                raise ValueError(f"Line {line}: building, floor, wing and group names are required")
            row["student_email"] = row["student_email"].lower()
            row["moderator_email"] = row["moderator_email"].lower()
            row["line_no"] = line
            rows.append(row)
        if not rows:
            raise ValueError("CSV contains no mapping rows")
        return rows

def validate(rows):
    groups, group_location, location_group, student_location = defaultdict(set), {}, {}, {}
    moderators = defaultdict(set)
    for row in rows:
        loc = (row["building_name"].casefold(), row["floor_name"].casefold(), row["wing_name"].casefold())
        group = row["hmc_group_name"].casefold()
        if group in group_location and group_location[group] != loc[:2]:
            raise ValueError(f"Line {row['line_no']}: an HMC group must belong to one building and floor")
        group_location[group] = loc[:2]
        groups[group].add(loc[2])
        if len(groups[group]) > 2:
            raise ValueError(f"Line {row['line_no']}: HMC group '{row['hmc_group_name']}' has more than two wings")
        if loc in location_group and location_group[loc] != group:
            raise ValueError(f"Line {row['line_no']}: this building/floor/wing is mapped to multiple HMC groups")
        location_group[loc] = group
        if row["student_email"]:
            old = student_location.get(row["student_email"])
            if old is not None and old != loc:
                raise ValueError(f"Line {row['line_no']}: student {row['student_email']} has multiple residence locations")
            student_location[row["student_email"]] = loc
        if row["moderator_email"]:
            moderators[group].add(row["moderator_email"])
    return groups, student_location, moderators

def by_name(db: Session, model, name: str, **filters):
    query = db.query(model).filter(func.lower(model.name) == name.casefold())
    for key, value in filters.items():
        query = query.filter(getattr(model, key) == value)
    matches = query.all()
    if len(matches) > 1:
        raise ValueError(f"Ambiguous existing {model.__name__} named {name!r}")
    return matches[0] if matches else None

def import_rows(db: Session, rows, verified_by: User | None, *, update_student_assignments: bool, replace_hmc_mappings: bool):
    desired_groups, student_locations, moderators = validate(rows)
    buildings, floors, wings, groups = {}, {}, {}, {}
    created_buildings = created_floors = created_wings = created_groups = assignments = moderator_count = 0
    for row in rows:
        bkey = row["building_name"].casefold()
        building = buildings.get(bkey) or by_name(db, Building, row["building_name"])
        if building is None:
            building = Building(name=row["building_name"]); db.add(building); db.flush(); created_buildings += 1
        buildings[bkey] = building
        fkey = (bkey, row["floor_name"].casefold())
        floor = floors.get(fkey) or by_name(db, Floor, row["floor_name"], building_id=building.id)
        if floor is None:
            floor = Floor(name=row["floor_name"], building_id=building.id); db.add(floor); db.flush(); created_floors += 1
        floors[fkey] = floor
        wkey = (bkey, row["wing_name"].casefold())
        wing = wings.get(wkey) or by_name(db, Wing, row["wing_name"], building_id=building.id)
        if wing is None:
            wing = Wing(name=row["wing_name"], building_id=building.id); db.add(wing); db.flush(); created_wings += 1
        wings[wkey] = wing
        gkey = row["hmc_group_name"].casefold()
        group = groups.get(gkey) or by_name(db, HMCGroup, row["hmc_group_name"])
        if group is None:
            group = HMCGroup(name=row["hmc_group_name"], building_id=building.id, floor_id=floor.id); db.add(group); db.flush(); created_groups += 1
        elif group.building_id != building.id or group.floor_id != floor.id:
            raise ValueError(f"Existing HMC group {group.name!r} is configured for a different building/floor")
        groups[gkey] = group
        existing = db.query(HMCGroupWing).filter(HMCGroupWing.building_id == building.id,
            HMCGroupWing.floor_id == floor.id, HMCGroupWing.wing_id == wing.id).first()
        if existing and existing.hmc_group_id != group.id:
            if not replace_hmc_mappings:
                raise ValueError(f"Wing {wing.name!r} on {building.name} floor {floor.name} belongs to a different group; use --replace-hmc-mappings only after verifying the full CSV")
            db.delete(existing); db.flush(); existing = None
        if existing is None:
            db.add(HMCGroupWing(hmc_group_id=group.id, building_id=building.id, floor_id=floor.id, wing_id=wing.id))
            db.flush()

    if verified_by is None:
        raise ValueError("--apply requires an active admin in --verified-by-email so imported residences have an auditable verifier")

    for email, loc in student_locations.items():
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is None or user.role != "student" or not user.is_active:
            raise ValueError(f"Student account {email!r} does not exist, is inactive, or is not a student")
        building = buildings[loc[0]]; floor = floors[(loc[0], loc[1])]; wing = wings[(loc[0], loc[2])]
        same = (user.residence_building_id, user.residence_floor_id, user.wing_id) == (building.id, floor.id, wing.id)
        if not same and any((user.residence_building_id, user.residence_floor_id, user.wing_id)) and not update_student_assignments:
            raise ValueError(f"Student {email!r} already has a different location; use --update-student-assignments after verification")
        user.residence_building_id = building.id; user.residence_floor_id = floor.id; user.wing_id = wing.id
        user.residence_verified_at = datetime.now(timezone.utc); user.residence_verified_by_id = verified_by.id
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
    # Historic location-specific requests remain hidden until a real, unambiguous mapping is reviewed.
    legacy_pending = db.query(Complaint).filter(Complaint.is_public.is_(True),
        Complaint.publication_status == "pending_mapping").all()
    remapped = 0
    for complaint in legacy_pending:
        building = by_name(db, Building, complaint.hostel) if complaint.hostel else None
        floor = by_name(db, Floor, complaint.floor, building_id=building.id) if building and complaint.floor else None
        wing = by_name(db, Wing, complaint.wing, building_id=building.id) if building and complaint.wing else None
        if building and floor and (not complaint.wing or wing):
            complaint.affected_building_id = building.id; complaint.affected_floor_id = floor.id
            complaint.affected_wing_id = wing.id if wing else None
            complaint.visibility_scope = "hmc_group_public"
            complaint.feed_review_status = "pending"
            complaint.publication_status = "pending_review"
            remapped += 1
    return created_buildings, created_floors, created_wings, created_groups, assignments, moderator_count, remapped

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is a dry run")
    parser.add_argument("--verified-by-email", help="Active administrator email recorded as verifier; required with --apply")
    parser.add_argument("--update-student-assignments", action="store_true")
    parser.add_argument("--replace-hmc-mappings", action="store_true")
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
        if args.apply and verifier is None:
            raise ValueError("--apply requires --verified-by-email with an active administrator account")
        result = import_rows(db, rows, verifier, update_student_assignments=args.update_student_assignments,
            replace_hmc_mappings=args.replace_hmc_mappings)
        labels = ("buildings created", "floors created", "wings created", "HMC groups created",
                  "student residences verified", "moderators added", "legacy complaints remapped to pending review")
        for label, count in zip(labels, result): print(f"{label}: {count}")
        if args.apply:
            db.commit(); print("Import committed.")
        else:
            db.rollback(); print("DRY RUN ONLY — no changes committed. Re-run with --apply after verifying the official roster.")
    except Exception as exc:
        db.rollback(); print(f"Import aborted: {exc}", file=sys.stderr); return 2
    finally:
        db.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
