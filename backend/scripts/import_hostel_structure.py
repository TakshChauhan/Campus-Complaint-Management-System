"""Import the official hostel/wing/floor CSV safely.

Default mode is read-only.  Use ``--apply`` only after reviewing the dry run;
it requires typing ``APPLY`` and commits one transaction.  Rows missing from
the authoritative CSV are deactivated, never deleted.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing

FIELDS = ("hostel_code", "hostel_name", "wing_code", "wing_name", "floor_code", "floor_name")
MAX_LENGTHS = {"hostel_code": 32, "hostel_name": 100, "wing_code": 32,
               "wing_name": 100, "floor_code": 32, "floor_name": 100}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"CSV columns must be exactly: {', '.join(FIELDS)}")
        rows = []
        for line, raw in enumerate(reader, start=2):
            row = {field: " ".join((raw.get(field) or "").split()) for field in FIELDS}
            for field, limit in MAX_LENGTHS.items():
                if not row[field] or len(row[field]) > limit:
                    raise ValueError(f"line {line}: {field} must be 1-{limit} characters")
            for field in ("hostel_code", "wing_code", "floor_code"):
                if row[field] != row[field].upper():
                    raise ValueError(f"line {line}: {field} must be uppercase")
            row["line"] = str(line)
            rows.append(row)
    if not rows:
        raise ValueError("CSV contains no rows")
    return rows


def validate_rows(rows: list[dict[str, str]]) -> None:
    seen_floors: set[tuple[str, str, str]] = set()
    hostel_names: dict[str, str] = {}
    wing_hosts: dict[str, str] = {}
    wing_names: dict[str, str] = {}
    for row in rows:
        location = (row["hostel_code"], row["wing_code"], row["floor_code"])
        if location in seen_floors:
            raise ValueError(f"line {row['line']}: duplicate hostel/wing/floor")
        seen_floors.add(location)
        if hostel_names.setdefault(row["hostel_code"], row["hostel_name"]) != row["hostel_name"]:
            raise ValueError(f"line {row['line']}: hostel has multiple names")
        if wing_hosts.setdefault(row["wing_code"], row["hostel_code"]) != row["hostel_code"]:
            raise ValueError(f"line {row['line']}: wing belongs to multiple hostels")
        if wing_names.setdefault(row["wing_code"], row["wing_name"]) != row["wing_name"]:
            raise ValueError(f"line {row['line']}: wing has multiple names")


def import_rows(db: Session, rows: list[dict[str, str]]) -> dict[str, int]:
    validate_rows(rows)
    wanted_hostels = {row["hostel_code"] for row in rows}
    wanted_wings = {row["wing_code"] for row in rows}
    wanted_floors = {(row["wing_code"], row["floor_code"]) for row in rows}
    hostels: dict[str, Hostel] = {}
    wings: dict[str, HostelWing] = {}
    counts = {"hostels_created": 0, "wings_created": 0, "floors_created": 0,
              "hostels_deactivated": 0, "wings_deactivated": 0, "floors_deactivated": 0}

    for row in rows:
        hostel = hostels.get(row["hostel_code"]) or db.query(Hostel).filter(Hostel.code == row["hostel_code"]).one_or_none()
        if hostel is None:
            hostel = Hostel(code=row["hostel_code"], name=row["hostel_name"], is_active=True)
            db.add(hostel); db.flush(); counts["hostels_created"] += 1
        elif hostel.name != row["hostel_name"]:
            raise ValueError(f"hostel {hostel.code} name differs from CSV")
        hostel.is_active = True
        hostels[row["hostel_code"]] = hostel

        wing = wings.get(row["wing_code"]) or db.query(HostelWing).filter(HostelWing.code == row["wing_code"]).one_or_none()
        if wing is None:
            wing = HostelWing(hostel_id=hostel.id, code=row["wing_code"], name=row["wing_name"], is_active=True)
            db.add(wing); db.flush(); counts["wings_created"] += 1
        elif wing.hostel_id != hostel.id or wing.name != row["wing_name"]:
            raise ValueError(f"wing {wing.code} differs from CSV")
        wing.is_active = True
        wings[row["wing_code"]] = wing

        floor = db.query(HostelFloor).filter(HostelFloor.wing_id == wing.id, HostelFloor.code == row["floor_code"]).one_or_none()
        if floor is None:
            floor = HostelFloor(wing_id=wing.id, code=row["floor_code"], name=row["floor_name"], is_active=True)
            db.add(floor); counts["floors_created"] += 1
        elif floor.name != row["floor_name"]:
            raise ValueError(f"floor {row['wing_code']}/{row['floor_code']} differs from CSV")
        floor.is_active = True

    for hostel in db.query(Hostel).all():
        if hostel.code not in wanted_hostels and hostel.is_active:
            hostel.is_active = False; counts["hostels_deactivated"] += 1
    for wing in db.query(HostelWing).all():
        if wing.code not in wanted_wings and wing.is_active:
            wing.is_active = False; counts["wings_deactivated"] += 1
    for floor in db.query(HostelFloor).all():
        key = (floor.wing.code, floor.code)
        if key not in wanted_floors and floor.is_active:
            floor.is_active = False; counts["floors_deactivated"] += 1
    db.flush()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        rows = read_rows(args.csv_path)
        validate_rows(rows)
        db = SessionLocal()
        try:
            counts = import_rows(db, rows)
            print("\n".join(f"{key}: {value}" for key, value in counts.items()))
            if not args.apply:
                db.rollback(); print("DRY RUN ONLY - no changes committed.")
                return 0
            if input("Type APPLY to commit: ").strip() != "APPLY":
                db.rollback(); print("Apply cancelled.")
                return 1
            db.commit(); print("Import committed.")
            return 0
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        print(f"Import aborted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
