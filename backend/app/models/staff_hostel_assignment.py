"""Assignment of staff members to hostels they support."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class StaffHostelAssignment(Base):
    __tablename__ = "staff_hostel_assignments"
    __table_args__ = (UniqueConstraint("user_id", "hostel_id", name="uq_staff_hostel_assignments_user_hostel"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    hostel_id = Column(Integer, ForeignKey("hostels.id", ondelete="RESTRICT"), nullable=False)
    assigned_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user = relationship("User", back_populates="hostel_assignments", foreign_keys=[user_id])
    hostel = relationship("Hostel", back_populates="staff_assignments")
    assigned_by = relationship("User", back_populates="created_hostel_assignments", foreign_keys=[assigned_by_id])
