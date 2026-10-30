"""Department-scoped staff complaint query operations.

Status-transition and status-history writes belong in the shared lifecycle
service. This module intentionally contains only read/query behavior for the
staff queue and complaint detail endpoints.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.user import User
from app.schemas.staff import StaffComplaintDetail, StaffComplaintQueueItem


def require_assigned_department(staff: User) -> int:
    """Return the authenticated staff member's assigned department or deny access."""
    if staff.department_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff account is not assigned to a department.",
        )
    return staff.department_id


def _queue_item(complaint: Complaint) -> StaffComplaintQueueItem:
    return StaffComplaintQueueItem(
        id=complaint.id,
        title=complaint.title,
        description_preview=(complaint.description or "")[:160],
        department_id=complaint.department_id,
        department_name=complaint.department.name if complaint.department else "Unknown",
        status=complaint.status,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
        floor_id=complaint.floor_id,
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
    )


def _detail(complaint: Complaint) -> StaffComplaintDetail:
    return StaffComplaintDetail(
        id=complaint.id,
        title=complaint.title,
        description=complaint.description,
        department_id=complaint.department_id,
        department_name=complaint.department.name if complaint.department else "Unknown",
        status=complaint.status,
        is_public=complaint.is_public,
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
        reopen_count=complaint.reopen_count,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )


def list_department_complaints(
    db: Session,
    staff: User,
    *,
    status_filter: str | None,
    hostel_id: int | None = None,
    limit: int,
    offset: int,
) -> tuple[list[StaffComplaintQueueItem], int]:
    """List only complaints assigned to the staff member's own department."""
    department_id = require_assigned_department(staff)
    query = db.query(Complaint).filter(Complaint.department_id == department_id)
    if status_filter is not None:
        query = query.filter(Complaint.status == status_filter)
    if hostel_id is not None:
        # Inner joins drop complaints without a canonical floor_id.
        query = (
            query.join(HostelFloor, Complaint.floor_id == HostelFloor.id)
            .join(HostelWing, HostelFloor.wing_id == HostelWing.id)
            .filter(HostelWing.hostel_id == hostel_id)
        )

    total = query.order_by(None).count()
    complaints = (
        query.options(joinedload(Complaint.department))
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_queue_item(complaint) for complaint in complaints], total


def _get_department_complaint(db: Session, department_id: int, complaint_id: int) -> Complaint:
    """Apply the complaint ID and department restriction together in SQL."""
    complaint = (
        db.query(Complaint)
        .options(joinedload(Complaint.department))
        .filter(
            Complaint.id == complaint_id,
            Complaint.department_id == department_id,
        )
        .first()
    )
    if complaint is None:
        # Do not disclose whether an out-of-department complaint exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")
    return complaint


def get_department_complaint(
    db: Session,
    staff: User,
    complaint_id: int,
) -> StaffComplaintDetail:
    """Return a complaint only if it belongs to the staff member's department."""
    department_id = require_assigned_department(staff)
    complaint = _get_department_complaint(db, department_id, complaint_id)
    return _detail(complaint)
