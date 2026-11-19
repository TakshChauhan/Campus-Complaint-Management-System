from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, SmallInteger, Text, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ComplaintFeedback(Base):
    __tablename__ = "complaint_feedback"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_complaint_feedback_rating"),
        CheckConstraint("comment IS NULL OR length(comment) <= 500", name="ck_complaint_feedback_comment_length"),
    )

    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False, unique=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rating = Column(SmallInteger, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    complaint = relationship("Complaint", back_populates="feedback")
    student = relationship("User", back_populates="complaint_feedback")
