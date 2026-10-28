
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.hostel_floor import HostelFloor
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintLocation,
    ComplaintListItem,
    ComplaintResponse,
)
from app.services.complaint_lifecycle_service import (
    calculate_rolling_resolution_metrics,
    get_public_complaints_feed,
    reopen_student_complaint,
    update_department_complaint_status,
)
from app.services.location_service import get_active_floor, is_hostel_department
from app.services.public_feed_service import add_responsible_audience, classify_complaint_visibility

logger = logging.getLogger("ccms.complaint_service")



def _canonical_complaint_location(db: Session, floor_id: int | None) -> ComplaintLocation | None:
    if floor_id is None:
        return None
    floor = db.query(HostelFloor).filter(HostelFloor.id == floor_id).first()
    if floor is None:
        return None
    return ComplaintLocation(
        hostel=floor.wing.hostel.name,
        wing=floor.wing.name,
        floor=floor.name,
    )


def create_student_complaint(
    db: Session,
    complaint_in: ComplaintCreate,
    student: User,
) -> ComplaintResponse:
    """Create a complaint at its affected location and classify feed publication."""

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

    is_hostel = is_hostel_department(department)

    # Location is where the issue occurred, never the reporter's residence.
    floor = None
    if complaint_in.floor_id is not None:
        floor = get_active_floor(db, complaint_in.floor_id)
        if floor is None:
            raise HTTPException(status_code=422, detail="Invalid or inactive floor_id.")
    elif is_hostel and settings.HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID:
        raise HTTPException(status_code=422, detail="floor_id is required for Hostel complaints.")

    # Unlocated Hostel complaints stay creatable for older clients, but are
    # classified pending_mapping and never published.
    location = _canonical_complaint_location(db, floor.id) if floor else None
    visibility = classify_complaint_visibility(
        db,
        student,
        is_public=complaint_in.is_public,
        floor=floor,
        has_legacy_location=any((complaint_in.hostel, complaint_in.wing, complaint_in.floor)),
        is_hostel=is_hostel,
    )
    now = datetime.now(timezone.utc)

    complaint = Complaint(
        title=complaint_in.title,
        description=complaint_in.description,
        department_id=department.id,
        created_by_id=student.id,
        status="submitted",
        is_public=complaint_in.is_public,
        hostel=location.hostel if location else complaint_in.hostel,
        wing=location.wing if location else complaint_in.wing,
        floor=location.floor if location else complaint_in.floor,
        floor_id=floor.id if floor else None,
        visibility_scope=visibility.visibility_scope,
        feed_review_status=visibility.feed_review_status,
        publication_status=visibility.publication_status,
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

        if visibility.audience_group_id is not None:
            # Auto-publish by a verified member authorizes their own group only.
            add_responsible_audience(db, complaint.id, visibility.audience_group_id, student.id)

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
        location=location,
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
        reopen_count=complaint.reopen_count,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
        floor_id=complaint.floor_id,
        visibility_scope=complaint.visibility_scope,
        feed_review_status=complaint.feed_review_status,
        publication_status=complaint.publication_status,
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
            publication_status=c.publication_status,
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
        location=_canonical_complaint_location(db, complaint.floor_id),
        hostel=complaint.hostel,
        wing=complaint.wing,
        floor=complaint.floor,
        reopen_count=complaint.reopen_count,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
        floor_id=complaint.floor_id,
        visibility_scope=complaint.visibility_scope,
        feed_review_status=complaint.feed_review_status,
        publication_status=complaint.publication_status,
    )
