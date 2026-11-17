from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, CheckConstraint, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ComplaintComment(Base):
    __tablename__ = "complaint_comments"
    __table_args__ = (
        CheckConstraint("length(body) BETWEEN 1 AND 1000", name="ck_complaint_comments_body_length"),
        Index("ix_complaint_comments_complaint_created_id", "complaint_id", "created_at", "id"),
    )

    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    complaint = relationship("Complaint", back_populates="comments")
    author = relationship("User", back_populates="complaint_comments")
