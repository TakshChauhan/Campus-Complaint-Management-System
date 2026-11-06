"""Hostel scope evaluation and query filtering for staff and administrators."""

from dataclasses import dataclass
from typing import Optional, Set, Type

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.user import User
from app.repositories.staff_hostel_assignment_repository import get_hostels_for_staff
from app.services.location_service import is_hostel_staff


@dataclass(frozen=True)
class StaffScope:
    """Encapsulates a user's authorization scope over hostel-related resources."""

    is_admin: bool
    is_hostel_staff: bool
    hostel_ids: Set[int]
    department_id: Optional[int] = None


def get_staff_scope(db: Session, user: Optional[User]) -> StaffScope:
    """Determine the user's department and the set of hostel IDs they cover.

    Rules:
    - Unauthenticated/None user: empty, no access.
    - Admin: universal access across all hostels (is_admin=True, hostel_ids contains all active hostels).
    - Hostel Department Staff: is_hostel_staff=True, hostel_ids contains active hostels assigned to them.
      If no hostels are assigned, hostel_ids is empty (fail closed).
    - Staff from non-Hostel departments: is_hostel_staff=False, hostel_ids is empty.
      Preserves existing department-specific behaviour without imposing hostel restrictions.
    - Other users (e.g. students): is_admin=False, is_hostel_staff=False, hostel_ids is empty.
    """
    if user is None:
        return StaffScope(is_admin=False, is_hostel_staff=False, hostel_ids=set(), department_id=None)

    # 1. Admin access
    if user.role == "admin":
        active_hostels = db.query(Hostel.id).filter(Hostel.is_active.is_(True)).all()
        all_active_hostel_ids = {h_id for (h_id,) in active_hostels}
        return StaffScope(
            is_admin=True,
            is_hostel_staff=False,
            hostel_ids=all_active_hostel_ids,
            department_id=user.department_id,
        )

    # 2. Hostel Department Staff
    if is_hostel_staff(db, user):
        assigned_hostels = get_hostels_for_staff(db, user.id)
        active_assigned_ids = {h.id for h in assigned_hostels if h.is_active}
        return StaffScope(
            is_admin=False,
            is_hostel_staff=True,
            hostel_ids=active_assigned_ids,
            department_id=user.department_id,
        )

    # 3. Staff from non-Hostel departments or other roles
    return StaffScope(
        is_admin=False,
        is_hostel_staff=False,
        hostel_ids=set(),
        department_id=user.department_id,
    )


def apply_scope(query: Query, scope: StaffScope, model: Optional[Type] = None) -> Query:
    """Filter a SQLAlchemy query according to the provided StaffScope.

    - Admin: returned unmodified (sees all hostels and unlocated records).
    - Non-hostel staff: returned unmodified (existing department-level filters apply).
    - Hostel staff:
        - If assigned to no hostels: returns empty result (fail-closed).
        - If assigned to hostels: joins through HostelFloor and HostelWing,
          filtering by HostelWing.hostel_id IN (scope.hostel_ids).
    """
    # Admin and non-hostel department staff are not restricted by hostel assignments
    if scope.is_admin or not scope.is_hostel_staff:
        return query

    # Hostel staff with 0 assigned hostels: fail closed (return zero records)
    if not scope.hostel_ids:
        return query.filter(false())

    # Resolve target entity to join
    entity = model
    if entity is None and hasattr(query, "column_descriptions") and query.column_descriptions:
        for desc in query.column_descriptions:
            ent = desc.get("entity")
            if ent is not None and hasattr(ent, "floor_id"):
                entity = ent
                break

    if entity is None:
        raise ValueError("Could not determine an entity with 'floor_id' on query. Provide 'model' explicitly.")

    return (
        query.join(HostelFloor, entity.floor_id == HostelFloor.id)
        .join(HostelWing, HostelFloor.wing_id == HostelWing.id)
        .filter(HostelWing.hostel_id.in_(scope.hostel_ids))
    )

