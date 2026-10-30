"""Complaint lifecycle state machine, atomic status history, reopen rules, public feed, and resolution metrics."""

from datetime import datetime, timedelta, timezone
import statistics
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, update
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.user import User
from app.schemas.staff import StaffComplaintDetail, StaffComplaintStatusUpdate
from app.services.public_feed_service import department_feed_conditions

# Lifecycle Rules
MAX_REOPEN_COUNT = 2
REOPEN_WINDOW_DAYS = 7
DEFAULT_ROLLING_WINDOW_DAYS = 30

# Permitted state transitions for staff
STAFF_ALLOWED_TRANSITIONS = {
    "submitted": ["in_progress"],
    "in_progress": ["resolved"],
    "reopened": ["in_progress"],
}


def update_department_complaint_status(
    db: Session,
    staff: User,
    complaint_id: int,
    payload: StaffComplaintStatusUpdate,
) -> StaffComplaintDetail:
    """Atomically transition a complaint's status with staff remark and history write.

    Enforces:
    - Department isolation (staff can only update complaints within their department)
    - Valid lifecycle state machine transition
    - Timestamping and atomic ComplaintStatusHistory record insertion
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    if staff.department_id is None or complaint.department_id != staff.department_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    current_status = complaint.status
    target_status = payload.status

    allowed_targets = STAFF_ALLOWED_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_targets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid status transition from '{current_status}' to '{target_status}'. "
                f"Permitted transitions from '{current_status}': {allowed_targets or 'None'}."
            ),
        )

    now = datetime.now(timezone.utc)

    try:
        result = db.execute(
            update(Complaint)
            .where(
                Complaint.id == complaint_id,
                Complaint.department_id == staff.department_id,
                Complaint.status == current_status,
            )
            .values(
                status=target_status,
                updated_at=now,
                resolved_at=now if target_status == "resolved" else None,
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complaint changed. Refresh and try again.",
            )

        history_entry = ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=current_status,
            to_status=target_status,
            actor_id=staff.id,
            remark=payload.remark,
            created_at=now,
        )
        db.add(history_entry)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(complaint)

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


def reopen_student_complaint(
    db: Session,
    student: User,
    complaint_id: int,
    remark: Optional[str] = None,
) -> Complaint:
    """Enforce reopen rules: owner verification, 7-day window, max 2 reopens."""
    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id == complaint_id,
            Complaint.created_by_id == student.id,
        )
        .first()
    )
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    if complaint.status != "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only resolved complaints can be reopened. Current status is '{complaint.status}'.",
        )

    if complaint.reopen_count >= MAX_REOPEN_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Complaint has reached the maximum allowed reopens ({MAX_REOPEN_COUNT}).",
        )

    now = datetime.now(timezone.utc)
    if complaint.resolved_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reopen a complaint without a resolution timestamp.",
        )

    resolved_time = complaint.resolved_at
    if resolved_time.tzinfo is None:
        resolved_time = resolved_time.replace(tzinfo=timezone.utc)
    if now - resolved_time > timedelta(days=REOPEN_WINDOW_DAYS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reopen window expired. Complaints can only be reopened within {REOPEN_WINDOW_DAYS} days of resolution.",
        )

    old_status = complaint.status
    old_reopen_count = complaint.reopen_count

    try:
        result = db.execute(
            update(Complaint)
            .where(
                Complaint.id == complaint_id,
                Complaint.created_by_id == student.id,
                Complaint.status == "resolved",
                Complaint.reopen_count == old_reopen_count,
            )
            .values(
                status="reopened",
                reopen_count=old_reopen_count + 1,
                resolved_at=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complaint changed. Refresh and try again.",
            )

        history_entry = ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=old_status,
            to_status="reopened",
            actor_id=student.id,
            remark=(remark.strip() if remark and remark.strip() else "Student requested complaint reopen."),
            created_at=now,
        )
        db.add(history_entry)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(complaint)
    return complaint


def get_public_complaints_feed(
    db: Session,
    *,
    department_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    hostel: Optional[str] = None,
    wing: Optional[str] = None,
    floor: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Complaint], int]:
    """Retrieve public complaints feed filtered by department, status, hostel, wing, and floor.

    Guarantees:
    - Only published, department-wide (non-located, non-Hostel) complaints are
      returned; is_public=True alone is insufficient.
    - Department isolation: if department_id is supplied, restricts to that department.
    - Status filtering: matches exact status string if supplied.
    - Location filtering: case-insensitive trimmed matching for hostel, wing, floor.
    - Deterministic ordering: created_at DESC, id DESC.
    - Limit clamped between 1 and 100.
    - Returns (items, total_count).
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # is_public is only a request: return published, department-wide items only.
    query = (
        db.query(Complaint)
        .join(Department, Department.id == Complaint.department_id)
        .filter(*department_feed_conditions())
    )

    if department_id is not None:
        query = query.filter(Complaint.department_id == department_id)

    if status_filter and status_filter.strip():
        query = query.filter(Complaint.status == status_filter.strip())

    if hostel and hostel.strip():
        query = query.filter(func.lower(Complaint.hostel) == hostel.strip().lower())

    if wing and wing.strip():
        query = query.filter(func.lower(Complaint.wing) == wing.strip().lower())

    if floor and floor.strip():
        query = query.filter(func.lower(Complaint.floor) == floor.strip().lower())

    total = query.order_by(None).count()

    items = (
        query.options(joinedload(Complaint.department))
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return items, total


def calculate_rolling_resolution_metrics(
    db: Session,
    *,
    window_days: int = DEFAULT_ROLLING_WINDOW_DAYS,
    department_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate rolling average resolution time and statistics for resolved complaints.

    Rules:
    - Window: complaints with resolved_at within the last `window_days` days from now.
    - Department filter: if department_id is provided, scopes calculations to that department.
    - Resolution duration = resolved_at - created_at.
    - Excludes negative durations (clock skew / anomalies).
    - Returns structured metrics dictionary:
        - window_days (int)
        - department_id (int or None)
        - resolved_count (int)
        - average_resolution_hours (float or None)
        - average_resolution_days (float or None)
        - median_resolution_hours (float or None)
        - min_resolution_hours (float or None)
        - max_resolution_hours (float or None)
    """
    if window_days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="window_days must be a positive integer.",
        )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    query = db.query(Complaint).filter(
        Complaint.resolved_at.isnot(None),
        Complaint.resolved_at >= cutoff,
    )

    if department_id is not None:
        query = query.filter(Complaint.department_id == department_id)

    resolved_complaints = query.all()

    durations_seconds: List[float] = []
    for c in resolved_complaints:
        if c.resolved_at and c.created_at:
            r_at = c.resolved_at if c.resolved_at.tzinfo else c.resolved_at.replace(tzinfo=timezone.utc)
            c_at = c.created_at if c.created_at.tzinfo else c.created_at.replace(tzinfo=timezone.utc)
            diff = (r_at - c_at).total_seconds()
            if diff >= 0:
                durations_seconds.append(diff)

    resolved_count = len(durations_seconds)

    if resolved_count == 0:
        return {
            "window_days": window_days,
            "department_id": department_id,
            "resolved_count": 0,
            "average_resolution_hours": None,
            "average_resolution_days": None,
            "median_resolution_hours": None,
            "min_resolution_hours": None,
            "max_resolution_hours": None,
        }

    total_seconds = sum(durations_seconds)
    avg_seconds = total_seconds / resolved_count
    median_seconds = statistics.median(durations_seconds)
    min_seconds = min(durations_seconds)
    max_seconds = max(durations_seconds)

    return {
        "window_days": window_days,
        "department_id": department_id,
        "resolved_count": resolved_count,
        "average_resolution_hours": round(avg_seconds / 3600.0, 2),
        "average_resolution_days": round(avg_seconds / 86400.0, 2),
        "median_resolution_hours": round(median_seconds / 3600.0, 2),
        "min_resolution_hours": round(min_seconds / 3600.0, 2),
        "max_resolution_hours": round(max_seconds / 3600.0, 2),
    }
