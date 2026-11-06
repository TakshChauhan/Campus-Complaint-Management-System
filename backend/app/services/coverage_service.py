"""Service for identifying hostel coverage gaps (S4-07)."""

from typing import Any, Dict, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User

OPEN_STATUSES = ("submitted", "in_progress", "reopened")


def get_coverage_gaps(db: Session) -> List[Dict[str, Any]]:
    """List hostels that have open complaints and no active assigned staff.

    Open complaints are those with status in ('submitted', 'in_progress', 'reopened').
    Complaints are linked to hostels via their canonical floor_id -> wing_id -> hostel_id.
    Hostels are considered covered only when at least one active staff member is assigned.
    """
    assigned_hostel_ids_subquery = (
        db.query(StaffHostelAssignment.hostel_id)
        .join(User, User.id == StaffHostelAssignment.user_id)
        .filter(
            User.is_active.is_(True),
            User.role == "staff",
        )
        .distinct()
    )

    results = (
        db.query(
            Hostel.id.label("hostel_id"),
            Hostel.name.label("hostel_name"),
            func.count(Complaint.id).label("open_count"),
        )
        .join(HostelWing, HostelWing.hostel_id == Hostel.id)
        .join(HostelFloor, HostelFloor.wing_id == HostelWing.id)
        .join(Complaint, Complaint.floor_id == HostelFloor.id)
        .filter(
            Hostel.is_active.is_(True),
            Hostel.id.notin_(assigned_hostel_ids_subquery),
            Complaint.status.in_(OPEN_STATUSES),
        )
        .group_by(Hostel.id, Hostel.name)
        .having(func.count(Complaint.id) > 0)
        .order_by(func.count(Complaint.id).desc(), Hostel.id.asc())
        .all()
    )

    return [
        {
            "hostel_id": row.hostel_id,
            "hostel_name": row.hostel_name,
            "open_count": row.open_count,
        }
        for row in results
    ]
