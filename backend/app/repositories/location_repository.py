"""Read operations for the canonical hostel location hierarchy.

Repositories only load and resolve database records. Role and ownership
authorization belongs in the service or API layer that calls them.
"""

from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing


def _canonical_code(value: str) -> str:
    """Return the canonical representation used by the location tables."""
    return value.strip().upper()


def list_active_hostels(db: Session) -> list[Hostel]:
    """Return active hostels with only active wings and floors loaded."""
    return (
        db.query(Hostel)
        .filter(Hostel.is_active.is_(True))
        .options(
            selectinload(
                Hostel.wings.and_(HostelWing.is_active.is_(True))
            )
            .selectinload(
                HostelWing.floors.and_(HostelFloor.is_active.is_(True))
            )
        )
        .order_by(Hostel.code)
        .all()
    )


def resolve_active_floor(
    db: Session,
    hostel_code: str,
    wing_code: str,
    floor_code: str,
) -> HostelFloor | None:
    """Resolve a floor only when the floor and both parents are active.

    Input codes are trimmed and uppercased to match the database's canonical
    code constraints. Missing, blank, or inactive locations return ``None``.
    """
    if not all(
        isinstance(value, str) and value.strip()
        for value in (hostel_code, wing_code, floor_code)
    ):
        return None

    hostel_code = _canonical_code(hostel_code)
    wing_code = _canonical_code(wing_code)
    floor_code = _canonical_code(floor_code)

    return (
        db.query(HostelFloor)
        .join(HostelWing, HostelFloor.wing_id == HostelWing.id)
        .join(Hostel, HostelWing.hostel_id == Hostel.id)
        .options(joinedload(HostelFloor.wing).joinedload(HostelWing.hostel))
        .filter(
            Hostel.code == hostel_code,
            Hostel.is_active.is_(True),
            HostelWing.code == wing_code,
            HostelWing.is_active.is_(True),
            HostelFloor.code == floor_code,
            HostelFloor.is_active.is_(True),
        )
        .one_or_none()
    )


list_active_hierarchy = list_active_hostels

