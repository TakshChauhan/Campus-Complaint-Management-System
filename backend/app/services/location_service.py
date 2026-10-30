"""Canonical hostel location lookups shared by residences, complaints and feeds."""

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.user import User
from app.schemas.location import FloorNode, HostelNode, WingNode

HOSTEL_DEPARTMENT_NAME = "hostel"


def is_hostel_department(department: Optional[Department]) -> bool:
    return department is not None and (department.name or "").strip().casefold() == HOSTEL_DEPARTMENT_NAME


def hostel_department_name_matches():
    """SQL expression matching the seeded Hostel department by name."""
    return func.lower(func.trim(Department.name)) == HOSTEL_DEPARTMENT_NAME


def get_active_hostel_department(db: Session) -> Optional[Department]:
    return (
        db.query(Department)
        .filter(hostel_department_name_matches(), Department.is_active.is_(True))
        .first()
    )


def is_hostel_staff(db: Session, user: User) -> bool:
    """Staff assigned to the active Hostel department."""
    if user.role != "staff" or user.department_id is None:
        return False
    hostel = get_active_hostel_department(db)
    return hostel is not None and user.department_id == hostel.id


def get_active_floor(db: Session, floor_id: int) -> Optional[HostelFloor]:
    """Return a floor only when it, its wing and its hostel are all active."""
    return (
        db.query(HostelFloor)
        .join(HostelWing, HostelFloor.wing_id == HostelWing.id)
        .join(Hostel, HostelWing.hostel_id == Hostel.id)
        .options(joinedload(HostelFloor.wing).joinedload(HostelWing.hostel))
        .filter(
            HostelFloor.id == floor_id,
            HostelFloor.is_active.is_(True),
            HostelWing.is_active.is_(True),
            Hostel.is_active.is_(True),
        )
        .first()
    )


def get_active_hostel(db: Session, hostel_id: int) -> Optional[Hostel]:
    return db.query(Hostel).filter(Hostel.id == hostel_id, Hostel.is_active.is_(True)).first()


def list_active_hostel_tree(db: Session) -> List[HostelNode]:
    """Active hostels, each with only its active wings and their active floors."""
    hostels = db.query(Hostel).filter(Hostel.is_active.is_(True)).order_by(Hostel.name, Hostel.id).all()
    wings = (
        db.query(HostelWing)
        .filter(HostelWing.is_active.is_(True), HostelWing.hostel_id.in_([h.id for h in hostels]))
        .order_by(HostelWing.code, HostelWing.id)
        .all()
    ) if hostels else []
    floors = (
        db.query(HostelFloor)
        .filter(HostelFloor.is_active.is_(True), HostelFloor.wing_id.in_([w.id for w in wings]))
        .order_by(HostelFloor.code, HostelFloor.id)
        .all()
    ) if wings else []

    floors_by_wing: dict[int, list[FloorNode]] = {}
    for floor in floors:
        floors_by_wing.setdefault(floor.wing_id, []).append(
            FloorNode(id=floor.id, code=floor.code, name=floor.name)
        )
    wings_by_hostel: dict[int, list[WingNode]] = {}
    for wing in wings:
        wings_by_hostel.setdefault(wing.hostel_id, []).append(
            WingNode(id=wing.id, code=wing.code, name=wing.name, floors=floors_by_wing.get(wing.id, []))
        )
    return [
        HostelNode(id=h.id, code=h.code, name=h.name, wings=wings_by_hostel.get(h.id, []))
        for h in hostels
    ]
