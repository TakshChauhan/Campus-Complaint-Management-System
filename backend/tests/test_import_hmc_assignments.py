"""HMC roster importer on the canonical hierarchy (scripts/import_hmc_assignments.py)."""
import importlib.util
from pathlib import Path

import pytest

from app.models.complaint import Complaint
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.services.public_feed_service import student_hmc_group
from sprint3_hmc_world import make_user

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_hmc_assignments.py"
spec = importlib.util.spec_from_file_location("import_hmc_assignments", SCRIPT)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def _row(line, hostel, wing, floor, group, student="", moderator=""):
    return {"hostel_code": hostel, "wing_code": wing, "floor_code": floor, "hmc_group_name": group,
            "student_email": student, "moderator_email": moderator, "line_no": line}


@pytest.fixture
def hierarchy(db):
    hostel = Hostel(code="MH", name="Main Hostel")
    db.add(hostel)
    db.flush()
    wings = {c: HostelWing(hostel_id=hostel.id, code=c, name=f"Wing {c}") for c in "ABC"}
    db.add_all(wings.values())
    db.flush()
    floors = {f"{c}1": HostelFloor(wing_id=w.id, code="1", name="Floor 1") for c, w in wings.items()}
    floors["A2"] = HostelFloor(wing_id=wings["A"].id, code="2", name="Floor 2")
    db.add_all(floors.values())
    db.commit()
    return floors


def test_import_maps_canonical_floors_and_verifies_residences(db, hierarchy, admin_user):
    student = make_user(db, "roster.student", "student")
    moderator = make_user(db, "roster.mod", "staff")
    rows = [
        _row(2, "MH", "A", "1", "Floor 1 AB", student.email, moderator.email),
        _row(3, "MH", "B", "1", "Floor 1 AB"),
    ]
    assert importer.import_rows(db, rows, admin_user, update_student_assignments=False,
                                replace_hmc_mappings=False) == (1, 2, 1, 1)
    db.commit()
    group = db.query(HMCGroup).one()
    assert (group.floor_code, group.hostel_id) == ("1", hierarchy["A1"].wing.hostel_id)
    assert {m.floor_id for m in db.query(HMCGroupFloor)} == {hierarchy["A1"].id, hierarchy["B1"].id}
    residence = db.query(StudentResidence).filter_by(student_id=student.id).one()
    assert (residence.status, residence.verified_by_id) == ("verified", admin_user.id)
    assert student_hmc_group(db, student).id == group.id
    assert db.query(HMCGroupModerator).filter_by(user_id=moderator.id, hmc_group_id=group.id).count() == 1


@pytest.mark.parametrize("rows, message", [
    ([_row(2, "MH", "A", "1", "G"), _row(3, "MH", "B", "1", "G"), _row(4, "MH", "C", "1", "G")], "more than two wings"),
    ([_row(2, "MH", "A", "1", "G"), _row(3, "MH", "A", "2", "G")], "one hostel floor level"),
    ([_row(2, "MH", "A", "1", "G"), _row(3, "MH", "A", "1", "H")], "multiple HMC groups"),
    ([_row(2, "MH", "Z", "1", "G")], "No active canonical floor"),
])
def test_import_rejects_invalid_rosters_without_creating_locations(db, hierarchy, admin_user, rows, message):
    floors_before = db.query(HostelFloor).count()
    with pytest.raises(ValueError, match=message):
        importer.import_rows(db, rows, admin_user, update_student_assignments=False, replace_hmc_mappings=False)
    assert db.query(HostelFloor).count() == floors_before


def test_import_requires_an_admin_verifier_and_explicit_moves(db, hierarchy, admin_user):
    student = make_user(db, "mover", "student")
    with pytest.raises(ValueError, match="verified-by-email"):
        importer.import_rows(db, [_row(2, "MH", "A", "1", "G", student.email)], None,
                             update_student_assignments=False, replace_hmc_mappings=False)
    importer.import_rows(db, [_row(2, "MH", "A", "1", "G", student.email)], admin_user,
                         update_student_assignments=False, replace_hmc_mappings=False)
    with pytest.raises(ValueError, match="different residence"):
        importer.import_rows(db, [_row(2, "MH", "C", "1", "H", student.email)], admin_user,
                             update_student_assignments=False, replace_hmc_mappings=False)


def test_stage_legacy_complaints_only_queues_unambiguous_matches_for_review(
    db, hierarchy, student_user, seeded_departments,
):
    def legacy(hostel, wing, floor):
        complaint = Complaint(title="Legacy", description="Legacy text location.", department_id=seeded_departments["it"].id,
                              created_by_id=student_user.id, is_public=True, hostel=hostel, wing=wing, floor=floor,
                              publication_status="pending_mapping")
        db.add(complaint)
        return complaint
    exact = legacy("Main Hostel", "Wing B", "Floor 1")
    vague = legacy("Main Hostel", "B", "")
    unknown = legacy("Old Block", "Wing B", "Floor 1")
    db.commit()
    assert importer.stage_legacy_complaints(db) == 1
    assert (exact.floor_id, exact.publication_status, exact.hostel) == (hierarchy["B1"].id, "pending_review", "Main Hostel")
    assert vague.floor_id is None and unknown.floor_id is None
    assert vague.publication_status == unknown.publication_status == "pending_mapping"
