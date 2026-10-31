"""Read operations for student residence declarations."""

from sqlalchemy.orm import Session, joinedload

from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence


def get_student_residence(
    db: Session,
    student_id: int,
) -> StudentResidence | None:
    """Return a student's residence with its complete location hierarchy.

    Verification and active-location policy belong in the service layer.
    """
    return (
        db.query(StudentResidence)
        .options(
            joinedload(StudentResidence.floor)
            .joinedload(HostelFloor.wing)
            .joinedload(HostelWing.hostel)
        )
        .filter(StudentResidence.student_id == student_id)
        .one_or_none()
    )

