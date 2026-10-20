from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.user import User


class ComplaintStatusHistory(Base):
    __tablename__ = "complaint_status_history"

    id = Column(Integer, primary_key=True)
    complaint_id = Column(
        Integer,
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    complaint = relationship("Complaint", back_populates="status_history")
    actor = relationship("User")
