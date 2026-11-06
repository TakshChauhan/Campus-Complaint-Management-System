"""S3-03: location and residence repository behavior."""

from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.services.location_service import list_active_hostel_tree
from app.repositories.location_repository import (
    list_active_hostels,
    resolve_active_floor,
)
from app.repositories.residence_repository import get_student_residence


def _location_tree(db, *, code="H1", active_hostel=True, active_wing=True, active_floor=True):
    hostel = Hostel(code=code, name=f"Hostel {code}", is_active=active_hostel)
    wing = HostelWing(
        code=f"W{code[-1]}",
        name="Wing One",
        is_active=active_wing,
        hostel=hostel,
    )
    floor = HostelFloor(
        code=f"F{code[-1]}",
        name="Floor One",
        is_active=active_floor,
        wing=wing,
    )
    db.add(hostel)
    db.commit()
    return hostel, wing, floor


def test_list_active_hostels_excludes_inactive_nodes(db):
    active_hostel, active_wing, _ = _location_tree(db)
    inactive_hostel, _, _ = _location_tree(db, code="H2", active_hostel=False)
    inactive_wing = HostelWing(
        hostel_id=active_hostel.id,
        code="W3",
        name="Inactive Wing",
        is_active=False,
    )
    inactive_floor = HostelFloor(
        wing_id=active_wing.id,
        code="F3",
        name="Inactive Floor",
        is_active=False,
    )
    db.add_all([inactive_wing, inactive_floor])
    db.commit()

    hostels = list_active_hostels(db)

    assert [hostel.code for hostel in hostels] == ["H1"]
    assert [wing.code for wing in hostels[0].wings] == ["W1"]
    assert [floor.code for floor in hostels[0].wings[0].floors] == ["F1"]
    assert inactive_hostel.code not in [hostel.code for hostel in hostels]


def test_list_active_hostel_tree_restores_service_sorting(db):
    hostel_zulu = Hostel(code="H2", name="Zulu", is_active=True)
    hostel_alpha = Hostel(code="H1", name="Alpha", is_active=True)
    wing_zulu_two = HostelWing(code="Z2", name="Wing Two", is_active=True, hostel=hostel_zulu)
    wing_zulu_one = HostelWing(code="Z1", name="Wing One", is_active=True, hostel=hostel_zulu)
    wing_alpha_two = HostelWing(code="A2", name="Wing Two", is_active=True, hostel=hostel_alpha)
    wing_alpha_one = HostelWing(code="A1", name="Wing One", is_active=True, hostel=hostel_alpha)
    floor_zulu_two = HostelFloor(code="ZF2", name="Floor Two", is_active=True, wing=wing_zulu_two)
    floor_zulu_one = HostelFloor(code="ZF1", name="Floor One", is_active=True, wing=wing_zulu_two)
    floor_alpha_two = HostelFloor(code="AF2", name="Floor Two", is_active=True, wing=wing_alpha_one)
    floor_alpha_one = HostelFloor(code="AF1", name="Floor One", is_active=True, wing=wing_alpha_one)
    db.add_all([
        floor_zulu_two,
        floor_zulu_one,
        wing_zulu_two,
        wing_zulu_one,
        floor_alpha_two,
        floor_alpha_one,
        wing_alpha_two,
        wing_alpha_one,
        hostel_zulu,
        hostel_alpha,
    ])
    db.commit()

    tree = list_active_hostel_tree(db)

    assert [hostel.name for hostel in tree] == ["Alpha", "Zulu"]
    assert [wing.code for wing in tree[0].wings] == ["A1", "A2"]
    assert [floor.code for floor in tree[0].wings[0].floors] == ["AF1", "AF2"]


def test_resolve_active_floor_normalizes_codes_and_requires_active_parents(db):
    _, _, floor = _location_tree(db)

    resolved = resolve_active_floor(db, " h1 ", " w1 ", " f1 ")

    assert resolved is not None
    assert resolved.id == floor.id
    assert resolved.wing.hostel.code == "H1"

    floor.is_active = False
    db.commit()
    assert resolve_active_floor(db, "H1", "W1", "F1") is None


def test_resolve_active_floor_returns_none_for_missing_or_blank_codes(db):
    _location_tree(db)

    assert resolve_active_floor(db, "H1", "W1", "missing") is None
    assert resolve_active_floor(db, "H1", "", "F1") is None
    assert resolve_active_floor(db, None, "W1", "F1") is None


def test_get_student_residence_loads_complete_location_hierarchy(db, student_user):
    _, wing, floor = _location_tree(db)
    residence = StudentResidence(student_id=student_user.id, floor_id=floor.id)
    db.add(residence)
    db.commit()

    loaded = get_student_residence(db, student_user.id)

    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.floor.code == "F1"
    assert loaded.floor.wing.id == wing.id
    assert loaded.floor.wing.hostel.code == "H1"
    assert get_student_residence(db, 999999) is None

