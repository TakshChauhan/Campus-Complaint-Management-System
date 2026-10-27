"""A student's declared residence and its staff verification state."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class StudentResidence(Base):
    __tablename__ = "student_residences"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'verified', 'rejected')", name="ck_student_residences_status"),
        UniqueConstraint("student_id", name="uq_student_residences_student_id"),
        Index("ix_student_residences_floor_id", "floor_id"),
        Index("ix_student_residences_status_submitted_at", "status", "submitted_at", "id"),
    )

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    floor_id = Column(Integer, ForeignKey("hostel_floors.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    remark = Column(Text, nullable=True)
    verified_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    student = relationship("User", back_populates="residence", foreign_keys=[student_id])
    floor = relationship("HostelFloor", back_populates="residences")
    verified_by = relationship("User", back_populates="reviewed_residences", foreign_keys=[verified_by_id])
