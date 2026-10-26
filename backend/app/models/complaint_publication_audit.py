"""Append-only audit trail for public-feed review and unpublish actions."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class ComplaintPublicationAudit(Base):
    __tablename__ = "complaint_publication_audit"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    action = Column(String(24), nullable=False)
    previous_status = Column(String(24), nullable=False)
    new_status = Column(String(24), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    complaint = relationship("Complaint", back_populates="publication_audit")
    actor = relationship("User", foreign_keys=[actor_user_id])
