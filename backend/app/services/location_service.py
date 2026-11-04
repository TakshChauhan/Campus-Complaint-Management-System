"""Canonical hostel location lookups shared by residences, complaints and feeds."""

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.user import User
from app.repositories.location_repository import (
    get_active_floor as repository_get_active_floor,
    get_active_hostel as repository_get_active_hostel,
    list_active_hostels,
)
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
    return repository_get_active_floor(db, floor_id)


def get_active_hostel(db: Session, hostel_id: int) -> Optional[Hostel]:
    return repository_get_active_hostel(db, hostel_id)


def list_active_hostel_tree(db: Session) -> List[HostelNode]:
    """Active hostels, each with only its active wings and their active floors."""
    hostels = list_active_hostels(db)
    return [
        HostelNode(
            id=hostel.id,
            code=hostel.code,
            name=hostel.name,
            wings=[
                WingNode(
                    id=wing.id,
                    code=wing.code,
                    name=wing.name,
                    floors=[
                        FloorNode(id=floor.id, code=floor.code, name=floor.name)
                        for floor in wing.floors
                    ],
                )
                for wing in hostel.wings
            ],
        )
        for hostel in hostels
    ]
