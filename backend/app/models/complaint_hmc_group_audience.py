"""Explicit audience mapping for HMC-scoped complaints, especially shared-floor reports."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func

from app.db.base_class import Base


class ComplaintHMCGroupAudience(Base):
    __tablename__ = "complaint_hmc_group_audiences"
    __table_args__ = (
        UniqueConstraint(
            "complaint_id", "hmc_group_id",
            name="uq_complaint_hmc_group_audiences_complaint_group",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(
        Integer,
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hmc_group_id = Column(
        Integer,
        ForeignKey("hmc_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
