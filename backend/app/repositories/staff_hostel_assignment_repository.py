"""Read operations for staff-to-hostel assignments."""
from sqlalchemy.orm import Session
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User


def get_hostels_for_staff(db: Session, user_id: int) -> list[Hostel]:
    return (db.query(Hostel).join(StaffHostelAssignment, StaffHostelAssignment.hostel_id == Hostel.id)
            .filter(StaffHostelAssignment.user_id == user_id).order_by(Hostel.id).all())


def get_staff_for_hostel(db: Session, hostel_id: int) -> list[User]:
    return (db.query(User).join(StaffHostelAssignment, StaffHostelAssignment.user_id == User.id)
            .filter(StaffHostelAssignment.hostel_id == hostel_id).order_by(User.id).all())
