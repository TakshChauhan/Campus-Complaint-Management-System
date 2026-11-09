"""Hostel scope evaluation and query filtering for staff and administrators."""

from dataclasses import dataclass
from typing import Optional, Set, Type

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Query, Session

from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.user import User
from app.repositories.staff_hostel_assignment_repository import get_hostels_for_staff
from app.services.location_service import is_hostel_department


@dataclass(frozen=True)
class StaffScope:
    """Encapsulates a user's authorization scope over hostel-related resources."""

    is_admin: bool
    is_hostel_staff: bool
    hostel_ids: Set[int]
    department_id: Optional[int] = None
    is_authorized: bool = False


def get_staff_scope(db: Session, user: Optional[User]) -> StaffScope:
    """Determine the user's department and the set of hostel IDs they cover.

    Rules:
    - Unauthenticated/None user or inactive user: is_authorized=False (returns zero rows).
    - Student or non-staff/non-admin roles: is_authorized=False (returns zero rows).
    - Inactive department staff: is_authorized=False (fails closed to zero rows).
    - Admin (active): universal access across all hostels (is_admin=True, is_authorized=True,
      hostel_ids contains all active hostels).
    - Active Hostel Department Staff: is_authorized=True, is_hostel_staff=True,
      hostel_ids contains active hostels assigned to them. If unassigned, hostel_ids is empty
      (fails closed to zero rows).
    - Active Staff from non-Hostel departments: is_authorized=True, is_hostel_staff=False,
      hostel_ids is empty. Allowed through without hostel restrictions; the calling service
      must enforce its own department-specific filtering.
    """
    if user is None or not getattr(user, "is_active", True):
        return StaffScope(
            is_admin=False,
            is_hostel_staff=False,
            hostel_ids=set(),
            department_id=None,
            is_authorized=False,
        )

    # 1. Admin access
    if user.role == "admin":
        active_hostels = db.query(Hostel.id).filter(Hostel.is_active.is_(True)).all()
        all_active_hostel_ids = {h_id for (h_id,) in active_hostels}
        return StaffScope(
            is_admin=True,
            is_hostel_staff=False,
            hostel_ids=all_active_hostel_ids,
            department_id=user.department_id,
            is_authorized=True,
        )

    # 2. Staff user checks
    if user.role == "staff" and user.department_id is not None:
        dept = db.query(Department).filter(Department.id == user.department_id).first()
        if dept is None or not dept.is_active:
            # Staff belonging to an inactive department fail closed (return zero rows)
            return StaffScope(
                is_admin=False,
                is_hostel_staff=False,
                hostel_ids=set(),
                department_id=user.department_id,
                is_authorized=False,
            )

        if is_hostel_department(dept):
            assigned_hostels = get_hostels_for_staff(db, user.id)
            active_assigned_ids = {h.id for h in assigned_hostels if h.is_active}
            return StaffScope(
                is_admin=False,
                is_hostel_staff=True,
                hostel_ids=active_assigned_ids,
                department_id=dept.id,
                is_authorized=True,
            )

        # Active staff from non-Hostel department:
        # Allowed through without hostel filtering; the calling service must enforce department filtering.
        return StaffScope(
            is_admin=False,
            is_hostel_staff=False,
            hostel_ids=set(),
            department_id=dept.id,
            is_authorized=True,
        )

    # 3. Students, staff without department, or other unauthorized roles:
    # Fail closed (returns zero rows in apply_scope).
    return StaffScope(
        is_admin=False,
        is_hostel_staff=False,
        hostel_ids=set(),
        department_id=getattr(user, "department_id", None),
        is_authorized=False,
    )


def apply_scope(query: Query, scope: StaffScope, model: Optional[Type] = None) -> Query:
    """Filter a SQLAlchemy query according to the provided StaffScope.

    - Unauthorized users (students, None, inactive, unassigned staff, inactive department staff):
      Returns an empty query (zero rows).
    - Admin: returned unmodified (sees all hostels and unlocated records).
    - Non-hostel staff: returned unmodified without hostel filtering (the calling service
      must enforce its own department-level filtering).
    - Hostel staff:
        - If assigned to no hostels: returns empty result (zero rows, fail-closed).
        - If assigned to hostels: filters by entity.floor_id IN (subquery),
          avoiding join duplication when the outer query already joins HostelFloor / HostelWing.
    """
    # Students, unauthenticated / None users, or unauthorized roles receive zero rows
    if not scope.is_authorized:
        return query.filter(false())

    # Admins have universal access across all hostels
    if scope.is_admin:
        return query

    # Non-hostel staff are not filtered by hostel; the calling service must enforce department filtering
    if not scope.is_hostel_staff:
        return query

    # Hostel staff with 0 assigned hostels: fail closed (return zero records)
    if not scope.hostel_ids:
        return query.filter(false())

    # Resolve target entity to filter by floor_id
    entity = model
    if entity is None and hasattr(query, "column_descriptions") and query.column_descriptions:
        for desc in query.column_descriptions:
            ent = desc.get("entity")
            if ent is not None and hasattr(ent, "floor_id"):
                entity = ent
                break

    if entity is None:
        raise ValueError("Could not determine an entity with 'floor_id' on query. Provide 'model' explicitly.")

    # Use a subquery to avoid duplicate joins on HostelFloor / HostelWing
    floor_ids_subquery = (
        select(HostelFloor.id)
        .join(HostelWing, HostelFloor.wing_id == HostelWing.id)
        .filter(HostelWing.hostel_id.in_(scope.hostel_ids))
    )

    # If the entity supports legacy text-based hostel location (e.g. Complaint),
    # also permit legacy records without a canonical floor_id whose hostel name
    # matches one of the assigned hostels.
    if hasattr(entity, "hostel"):
        hostel_names_subquery = (
            select(Hostel.name)
            .filter(Hostel.id.in_(scope.hostel_ids))
        )
        return query.filter(
            or_(
                entity.floor_id.in_(floor_ids_subquery),
                and_(
                    entity.floor_id.is_(None),
                    entity.hostel.in_(hostel_names_subquery),
                ),
            )
        )

    return query.filter(entity.floor_id.in_(floor_ids_subquery))
