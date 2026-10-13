import logging
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.department import Department
from app.models.user import User
from app.schemas.complaint import ComplaintCreate, ComplaintListItem, ComplaintResponse

logger = logging.getLogger("ccms.complaint_service")


def create_student_complaint(
    db: Session,
    complaint_in: ComplaintCreate,
    student: User
) -> ComplaintResponse:
    """Create and persist a new complaint for the authenticated student."""
    # Validate department existence and operational status
    department = db.query(Department).filter(Department.id == complaint_in.department_id).first()
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

    complaint = Complaint(
        title=complaint_in.title,
        description=complaint_in.description,
        department_id=department.id,
        created_by_id=student.id,
        status="submitted",
    )

    db.add(complaint)
    try:
        db.commit()
        db.refresh(complaint)
    except Exception:
        logger.exception("Failed to record complaint in database for student_id=%s", student.id)
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
    )


def get_my_complaints(
    db: Session,
    student_id: int,
    limit: int = 50,
    offset: int = 0,
) -> List[ComplaintListItem]:
    """Retrieve personal complaint history for authenticated student sorted newest first with pagination."""
    complaints = (
        db.query(Complaint)
        .options(joinedload(Complaint.department))
        .filter(Complaint.created_by_id == student_id)
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        ComplaintListItem(
            id=c.id,
            title=c.title,
            department_name=c.department.name if c.department else "Unknown",
            status=c.status,
            created_at=c.created_at,
        )
        for c in complaints
    ]
