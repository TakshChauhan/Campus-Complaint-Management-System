"""Explicit designation of staff who may moderate publication for an HMC group."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class HMCGroupModerator(Base):
    __tablename__ = "hmc_group_moderators"
    __table_args__ = (UniqueConstraint("hmc_group_id", "user_id", name="uq_hmc_group_moderators_group_user"),)

    id = Column(Integer, primary_key=True, index=True)
    hmc_group_id = Column(Integer, ForeignKey("hmc_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    group = relationship("HMCGroup", back_populates="moderators")
    moderator = relationship("User", foreign_keys=[user_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])
