from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.complaint_status_history import ComplaintStatusHistory
    from app.models.department import Department
    from app.models.user import User


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        Index("ix_complaints_created_by_id_created_at", "created_by_id", "created_at"),
        CheckConstraint("visibility_scope IN ('private', 'department_public', 'hmc_group_public')", name="ck_complaints_visibility_scope"),
        CheckConstraint("feed_review_status IN ('not_required', 'pending', 'approved', 'auto_approved', 'rejected')", name="ck_complaints_feed_review_status"),
        CheckConstraint("publication_status IN ('private', 'pending_review', 'pending_mapping', 'published', 'rejected')", name="ck_complaints_publication_status"),
        CheckConstraint("(visibility_scope = 'private' AND is_public = false) OR (visibility_scope IN ('department_public', 'hmc_group_public') AND is_public = true)", name="ck_complaints_public_scope_consistency"),
        CheckConstraint("visibility_scope != 'department_public' OR (affected_building_id IS NULL AND affected_floor_id IS NULL AND affected_wing_id IS NULL AND trim(coalesce(hostel, '')) = '' AND trim(coalesce(wing, '')) = '' AND trim(coalesce(floor, '')) = '')", name="ck_complaints_department_public_no_location"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_complaints_created_by_id_users"),
        nullable=False,
        index=True,
    )
    status = Column(String(30), nullable=False, default="submitted", index=True)
    is_public = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Legacy text values remain for backwards-readable staff/history payloads.
    hostel = Column(String(100), nullable=True)
    wing = Column(String(50), nullable=True)
    floor = Column(String(20), nullable=True)
    affected_building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=True, index=True)
    affected_floor_id = Column(Integer, ForeignKey("floors.id", ondelete="RESTRICT"), nullable=True, index=True)
    affected_wing_id = Column(Integer, ForeignKey("wings.id", ondelete="RESTRICT"), nullable=True, index=True)
    visibility_scope = Column(String(24), nullable=False, default="private", server_default=text("'private'"), index=True)
    feed_review_status = Column(String(16), nullable=False, default="not_required", server_default=text("'not_required'"), index=True)
    publication_status = Column(String(24), nullable=False, default="private", server_default=text("'private'"), index=True)
    feed_reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    feed_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    feed_review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    reopen_count = Column(Integer, nullable=False, default=0, server_default=text("0"))

    # Relationships
    department = relationship("Department", back_populates="complaints")
    creator = relationship("User", back_populates="complaints", foreign_keys=[created_by_id])
    status_history = relationship(
        "ComplaintStatusHistory",
        back_populates="complaint",
        order_by="ComplaintStatusHistory.id",
        passive_deletes="all",
    )
    affected_building = relationship("Building", foreign_keys=[affected_building_id])
    affected_floor = relationship("Floor", foreign_keys=[affected_floor_id])
    affected_wing = relationship("Wing", foreign_keys=[affected_wing_id])
    feed_reviewed_by = relationship("User", foreign_keys=[feed_reviewed_by_id])
    publication_audit = relationship("ComplaintPublicationAudit", back_populates="complaint", order_by="ComplaintPublicationAudit.id", passive_deletes="all")
