"""Student residence submission and Hostel-department verification.

A residence is only an HMC membership source once Hostel staff or an admin
verifies it. Any change by the student returns it to ``pending``.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.residence import MyResidence, ResidenceDecision, StaffResidenceItem
from app.services.location_service import get_active_floor, is_hostel_staff


def require_hostel_staff_or_admin(db: Session, user: User) -> None:
    if user.role == "admin" or is_hostel_staff(db, user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only Hostel-department staff or administrators can review residences.",
    )


def _with_location(query):
    return query.options(
        joinedload(StudentResidence.floor).joinedload(HostelFloor.wing).joinedload(HostelWing.hostel),
        joinedload(StudentResidence.student),
    )


def _my_residence(residence: StudentResidence) -> MyResidence:
    floor = residence.floor
    return MyResidence(
        floor_id=floor.id,
        hostel=floor.wing.hostel.name,
        wing=floor.wing.name,
        floor=floor.name,
        status=residence.status,
        remark=residence.remark,
    )


def _staff_item(residence: StudentResidence) -> StaffResidenceItem:
    return StaffResidenceItem(
        **_my_residence(residence).model_dump(),
        id=residence.id,
        student_id=residence.student_id,
        student_name=residence.student.name,
        student_email=residence.student.email,
        submitted_at=residence.submitted_at,
        decided_at=residence.verified_at,
    )


def get_my_residence(db: Session, student: User) -> MyResidence:
    residence = _with_location(db.query(StudentResidence)).filter(
        StudentResidence.student_id == student.id
    ).first()
    if residence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No residence has been set.")
    return _my_residence(residence)


def set_my_residence(db: Session, student: User, floor_id: int) -> MyResidence:
    """Create or replace the student's residence; it always returns to pending."""
    floor = get_active_floor(db, floor_id)
    if floor is None:
        raise HTTPException(status_code=422, detail="Unknown or inactive floor_id.")

    now = datetime.now(timezone.utc)
    residence = db.query(StudentResidence).filter(StudentResidence.student_id == student.id).first()
    if residence is None:
        residence = StudentResidence(student_id=student.id, floor_id=floor.id)
        db.add(residence)
    residence.floor_id = floor.id
    residence.status = "pending"
    residence.remark = None
    residence.verified_by_id = None
    residence.verified_at = None
    residence.submitted_at = now
    residence.updated_at = now
    db.commit()
    return get_my_residence(db, student)


def list_residences(
    db: Session,
    reviewer: User,
    *,
    status_filter: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[StaffResidenceItem], int]:
    require_hostel_staff_or_admin(db, reviewer)
    query = db.query(StudentResidence).filter(StudentResidence.status == status_filter)
    total = query.order_by(None).count()
    rows = (
        _with_location(query)
        .order_by(StudentResidence.submitted_at.asc(), StudentResidence.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_staff_item(row) for row in rows], total


def decide_residence(
    db: Session,
    reviewer: User,
    residence_id: int,
    payload: ResidenceDecision,
) -> StaffResidenceItem:
    require_hostel_staff_or_admin(db, reviewer)
    residence: Optional[StudentResidence] = (
        db.query(StudentResidence).filter(StudentResidence.id == residence_id).first()
    )
    if residence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residence not found.")

    now = datetime.now(timezone.utc)
    # Conditional update: a concurrent decision or student change cannot be overwritten.
    result = db.execute(
        update(StudentResidence)
        .where(StudentResidence.id == residence_id, StudentResidence.status == "pending")
        .values(
            status="verified" if payload.decision == "approve" else "rejected",
            remark=payload.remark,
            verified_by_id=reviewer.id,
            verified_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        # Nothing was written, so there is nothing to roll back.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This residence is not pending; it has already been decided.",
        )
    db.commit()
    db.expire_all()
    residence = _with_location(db.query(StudentResidence)).filter(StudentResidence.id == residence_id).one()
    return _staff_item(residence)
