
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintListItem,
    ComplaintResponse,
)
from app.services.complaint_lifecycle_service import (
    calculate_rolling_resolution_metrics,
    get_public_complaints_feed,
    reopen_student_complaint,
    update_department_complaint_status,
)

logger = logging.getLogger("ccms.complaint_service")


def create_student_complaint(
    db: Session,
    complaint_in: ComplaintCreate,
    student: User,
) -> ComplaintResponse:
    """Create a complaint using the student's verified residence."""

    department = (
        db.query(Department)
        .filter(Department.id == complaint_in.department_id)
        .first()
    )

    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Department with ID {complaint_in.department_id} does not exist.",
        )

    if not department.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Department '{department.name}' is currently inactive and cannot receive complaints.",
        )

    # Derive canonical location from the student's verified residence.
    # Do not trust the legacy hostel/wing/floor text supplied by the client.
    residence = (
        db.query(StudentResidence)
        .join(
            HostelFloor,
            StudentResidence.floor_id == HostelFloor.id,
        )
        .join(
            HostelWing,
            HostelFloor.wing_id == HostelWing.id,
        )
        .join(
            Hostel,
            HostelWing.hostel_id == Hostel.id,
        )
        .filter(
            StudentResidence.student_id == student.id,
            StudentResidence.status == "verified",
            StudentResidence.verified_at.isnot(None),
            HostelFloor.is_active.is_(True),
            HostelWing.is_active.is_(True),
            Hostel.is_active.is_(True),
        )
        .first()
    )

    verified_floor_id = residence.floor_id if residence else None
    now = datetime.now(timezone.utc)

    complaint = Complaint(
        title=complaint_in.title,
        description=complaint_in.description,
        department_id=department.id,
        created_by_id=student.id,
        status="submitted",
        is_public=complaint_in.is_public,
        hostel=complaint_in.hostel,
        wing=complaint_in.wing,
        floor=complaint_in.floor,
        floor_id=verified_floor_id,
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(complaint)
        db.flush()

        initial_history = ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=None,
            to_status="submitted",
            actor_id=student.id,
            remark=None,
            created_at=now,
        )
        db.add(initial_history)

        db.commit()
        db.refresh(complaint)

    except Exception:
        logger.exception(
            "Failed to record complaint in database for student_id=%s",
            student.id,
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record complaint in database due to a transaction error.",
        )

    return ComplaintResponse(
        id=complaint.id,
        title=complaint.title,
        description=complaint.description,
        department_id=complaint.department_id,
        department_name=department.name,
        created_by_id=complaint.created_by_id,
        status=complaint.status,
        created_at=complaint.created_at,
        is_public=complaint.is_public,
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
        reopen_count=complaint.reopen_count,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )


PREVIEW_LENGTH = 160


def _preview(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[: PREVIEW_LENGTH - 1].rstrip() + "\u2026"


def _parse_reference(q: str) -> Optional[int]:
    """Interpret 'CMP-42', 'cmp42', '#42' or '42' as a complaint ID."""
    match = re.fullmatch(
        r"\s*(?:cmp[\s\-_]*|#)?(\d{1,9})\s*",
        q,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_my_complaints(
    db: Session,
    student_id: int,
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    department_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort: str = "newest",
) -> Tuple[List[ComplaintListItem], int]:
    """Return the student's complaint history with filtering and pagination."""

    query = db.query(Complaint).filter(
        Complaint.created_by_id == student_id
    )

    if q and q.strip():
        term = q.strip()
        ref_id = _parse_reference(term)
        pattern = f"%{_escape_like(term.lower())}%"

        text_match = or_(
            func.lower(Complaint.title).like(pattern, escape="\\"),
            func.lower(Complaint.description).like(pattern, escape="\\"),
        )

        query = query.filter(
            or_(Complaint.id == ref_id, text_match)
            if ref_id is not None
            else text_match
        )

    if department_id is not None:
        query = query.filter(
            Complaint.department_id == department_id
        )

    if date_from is not None:
        start = datetime.combine(
            date_from,
            time.min,
            tzinfo=timezone.utc,
        )
        query = query.filter(Complaint.created_at >= start)

    if date_to is not None:
        end = datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        query = query.filter(Complaint.created_at < end)

    total = query.order_by(None).count()

    if sort == "oldest":
        ordering = (
            Complaint.created_at.asc(),
            Complaint.id.asc(),
        )
    else:
        ordering = (
            Complaint.created_at.desc(),
            Complaint.id.desc(),
        )

    complaints = (
        query.options(joinedload(Complaint.department))
        .order_by(*ordering)
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        ComplaintListItem(
            id=c.id,
            title=c.title,
            description_preview=_preview(c.description),
            department_id=c.department_id,
            department_name=(
                c.department.name if c.department else "Unknown"
            ),
            status=c.status,
            created_at=c.created_at,
        )
        for c in complaints
    ]

    return items, total


def get_my_complaint(
    db: Session,
    student_id: int,
    complaint_id: int,
) -> ComplaintResponse:
    """Return one complaint owned by the student."""

    complaint = (
        db.query(Complaint)
        .options(joinedload(Complaint.department))
        .filter(
            Complaint.id == complaint_id,
            Complaint.created_by_id == student_id,
        )
        .first()
    )

    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    return ComplaintResponse(
        id=complaint.id,
        title=complaint.title,
        description=complaint.description,
        department_id=complaint.department_id,
        department_name=(
            complaint.department.name
            if complaint.department
            else "Unknown"
        ),
        created_by_id=complaint.created_by_id,
        status=complaint.status,
        created_at=complaint.created_at,
        is_public=complaint.is_public,
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
        reopen_count=complaint.reopen_count,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )
