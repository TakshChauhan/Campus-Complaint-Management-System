"""Tests for the production hostel structure importer."""

import csv
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing

from scripts import import_hostel_structure as importer


FIELDS = ("hostel_code", "hostel_name", "wing_code", "wing_name", "floor_code", "floor_name")


@pytest.fixture
def cli_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def row(hostel="OHM", wing="OHM-A", floor="1", *, hostel_name="Old Hostel", wing_name="Wing A", floor_name="Floor 1"):
    return {"hostel_code": hostel, "hostel_name": hostel_name, "wing_code": wing,
            "wing_name": wing_name, "floor_code": floor, "floor_name": floor_name, "line": "2"}


def test_read_rows_accepts_official_csv():
    path = Path(__file__).parents[1] / "app" / "scripts" / "data" / "dau_hostels.csv"
    rows = importer.read_rows(path)
    importer.validate_rows(rows)
    assert len(rows) == 18


@pytest.mark.parametrize("bad_field", ["hostel_code", "wing_code", "floor_code"])
def test_read_rows_rejects_non_uppercase_codes(tmp_path, bad_field):
    path = tmp_path / "bad.csv"
    values = dict(zip(FIELDS, ["OHM", "Old Hostel", "OHM-A", "Wing A", "1", "Floor 1"]))
    values[bad_field] = "g" if bad_field == "floor_code" else values[bad_field].lower()
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader(); writer.writerow(values)
    with pytest.raises(ValueError, match="uppercase"):
        importer.read_rows(path)


def test_validate_rows_rejects_duplicate_floor():
    with pytest.raises(ValueError, match="duplicate"):
        importer.validate_rows([row(), row()])


def test_validate_rows_rejects_wing_in_two_hostels():
    with pytest.raises(ValueError, match="multiple hostels"):
        importer.validate_rows([row(), row(hostel="NHM", wing="OHM-A")])


def test_import_creates_hierarchy(db):
    counts = importer.import_rows(db, [row(), row(floor="2", floor_name="Floor 2")])
    db.commit()
    assert counts["hostels_created"] == 1
    assert counts["wings_created"] == 1
    assert counts["floors_created"] == 2
    assert db.query(Hostel).one().is_active is True
    assert db.query(HostelWing).one().code == "OHM-A"
    assert db.query(HostelFloor).count() == 2


def test_import_reactivates_matching_rows_and_deactivates_missing_rows(db):
    hostel = Hostel(code="OLD", name="Old", is_active=True)
    db.add(hostel); db.flush()
    wing = HostelWing(hostel_id=hostel.id, code="OLD-A", name="Wing A", is_active=True)
    db.add(wing); db.flush()
    db.add(HostelFloor(wing_id=wing.id, code="1", name="Floor 1", is_active=True))
    db.commit()
    counts = importer.import_rows(db, [row()])
    db.commit()
    assert counts["hostels_deactivated"] == 1
    assert counts["wings_deactivated"] == 1
    assert counts["floors_deactivated"] == 1
    assert db.query(Hostel).filter_by(code="OLD").one().is_active is False
    assert db.query(HostelWing).filter_by(code="OLD-A").one().is_active is False
    assert db.query(HostelFloor).filter_by(wing_id=wing.id).one().is_active is False


def test_import_rejects_name_change_without_partial_commit(db):
    importer.import_rows(db, [row()])
    db.flush()
    with pytest.raises(ValueError, match="name differs"):
        importer.import_rows(db, [row(hostel_name="Changed")])
    assert db.query(Hostel).one().name == "Old Hostel"


def test_import_keeps_existing_matching_rows_active(db):
    importer.import_rows(db, [row()])
    db.commit()
    importer.import_rows(db, [row()])
    db.commit()
    assert db.query(Hostel).count() == 1
    assert db.query(HostelWing).count() == 1
    assert db.query(HostelFloor).count() == 1


@pytest.mark.parametrize("field", FIELDS)
def test_read_rows_rejects_missing_required_values(tmp_path, field):
    path = tmp_path / "missing.csv"
    values = dict(zip(FIELDS, ["OHM", "Old Hostel", "OHM-A", "Wing A", "1", "Floor 1"]))
    values[field] = ""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader(); writer.writerow(values)
    with pytest.raises(ValueError, match=field):
        importer.read_rows(path)


def test_validate_rows_rejects_multiple_hostel_names():
    with pytest.raises(ValueError, match="multiple names"):
        importer.validate_rows([row(), row(floor="2", hostel_name="Changed")])


def test_validate_rows_rejects_multiple_wing_names():
    with pytest.raises(ValueError, match="multiple names"):
        importer.validate_rows([row(), row(floor="2", wing_name="Changed")])


def test_import_updates_existing_inactive_hostel(db):
    db.add(Hostel(code="OHM", name="Old Hostel", is_active=False))
    db.flush()
    importer.import_rows(db, [row()])
    assert db.query(Hostel).one().is_active is True


def test_import_updates_existing_inactive_wing(db):
    hostel = Hostel(code="OHM", name="Old Hostel", is_active=True)
    db.add(hostel); db.flush()
    db.add(HostelWing(hostel_id=hostel.id, code="OHM-A", name="Wing A", is_active=False))
    db.flush()
    importer.import_rows(db, [row()])
    assert db.query(HostelWing).one().is_active is True


def test_import_updates_existing_inactive_floor(db):
    hostel = Hostel(code="OHM", name="Old Hostel", is_active=True)
    db.add(hostel); db.flush()
    wing = HostelWing(hostel_id=hostel.id, code="OHM-A", name="Wing A", is_active=True)
    db.add(wing); db.flush()
    db.add(HostelFloor(wing_id=wing.id, code="1", name="Floor 1", is_active=False))
    db.flush()
    importer.import_rows(db, [row()])
    assert db.query(HostelFloor).one().is_active is True


def test_cli_dry_run_rolls_back_changes(cli_db, monkeypatch, capsys):
    csv_path = Path(__file__).parents[1] / "app" / "scripts" / "data" / "dau_hostels.csv"
    monkeypatch.setattr(importer, "SessionLocal", lambda: cli_db)
    monkeypatch.setattr(sys, "argv", ["import_hostel_structure.py", str(csv_path)])

    assert importer.main() == 0
    assert cli_db.query(Hostel).count() == 0
    assert "DRY RUN ONLY" in capsys.readouterr().out


def test_cli_apply_requires_exact_confirmation(cli_db, monkeypatch, capsys):
    csv_path = Path(__file__).parents[1] / "app" / "scripts" / "data" / "dau_hostels.csv"
    monkeypatch.setattr(importer, "SessionLocal", lambda: cli_db)
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    monkeypatch.setattr(sys, "argv", ["import_hostel_structure.py", str(csv_path), "--apply"])

    assert importer.main() == 1
    assert cli_db.query(Hostel).count() == 0
    assert "Apply cancelled" in capsys.readouterr().out
