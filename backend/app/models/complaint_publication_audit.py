"""Append-only audit trail for public-feed review, unpublish and audience actions."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class ComplaintPublicationAudit(Base):
    __tablename__ = "complaint_publication_audit"
    __table_args__ = (
        Index("ix_complaint_publication_audit_complaint_id", "complaint_id"),
        Index("ix_complaint_publication_audit_actor_user_id", "actor_user_id"),
    )

    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action = Column(String(24), nullable=False)
    previous_status = Column(String(24), nullable=False)
    new_status = Column(String(24), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    complaint = relationship("Complaint", back_populates="publication_audit")
    actor = relationship("User", foreign_keys=[actor_user_id])
