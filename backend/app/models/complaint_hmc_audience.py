"""Explicit HMC groups a published complaint is authorized for.

A published HMC-scoped complaint is visible to a group only through one of these
rows. The responsible group's row is written on auto-publish or moderator
approval; any additional group on the same hostel floor level (a shared-floor
audience) requires a separate, audited moderator decision. Nothing is inferred
from a missing wing or from floor-level text.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ComplaintHMCAudience(Base):
    __tablename__ = "complaint_hmc_audiences"
    __table_args__ = (
        CheckConstraint("source IN ('responsible_group', 'shared_floor')", name="ck_complaint_hmc_audiences_source"),
        UniqueConstraint("complaint_id", "hmc_group_id", name="uq_complaint_hmc_audiences_complaint_group"),
        Index("ix_complaint_hmc_audiences_hmc_group_id", "hmc_group_id"),
    )

    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False)
    hmc_group_id = Column(Integer, ForeignKey("hmc_groups.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(24), nullable=False)
    decided_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    complaint = relationship("Complaint", back_populates="hmc_audiences")
    group = relationship("HMCGroup")
    decided_by = relationship("User", foreign_keys=[decided_by_id])
