"""HMC groups and the canonical hostel floors they manage.

A ``HostelFloor`` belongs to exactly one wing, so a group covering two wings on
the same floor level maps two ``HostelFloor`` rows. The service layer treats a
group as valid only when it has one or two active floors in distinct wings of
the group's hostel, all sharing the group's ``floor_code``.
"""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, true
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class HMCGroup(Base):
    __tablename__ = "hmc_groups"
    __table_args__ = (
        CheckConstraint("floor_code = upper(trim(floor_code)) AND length(floor_code) > 0", name="ck_hmc_groups_floor_code_canonical"),
        CheckConstraint("length(trim(name)) > 0", name="ck_hmc_groups_name_nonempty"),
        UniqueConstraint("name", name="uq_hmc_groups_name"),
        Index("ix_hmc_groups_hostel_id", "hostel_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    hostel_id = Column(Integer, ForeignKey("hostels.id", ondelete="RESTRICT"), nullable=False)
    # Shared floor level, matching HostelFloor.code of every mapped floor.
    floor_code = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hostel = relationship("Hostel")
    floor_assignments = relationship("HMCGroupFloor", back_populates="group", cascade="all, delete-orphan")
    moderators = relationship("HMCGroupModerator", back_populates="group", cascade="all, delete-orphan")


class HMCGroupFloor(Base):
    """Maps one canonical wing floor to the HMC group responsible for it."""

    __tablename__ = "hmc_group_floors"
    __table_args__ = (
        UniqueConstraint("floor_id", name="uq_hmc_group_floors_floor_id"),
        Index("ix_hmc_group_floors_hmc_group_id", "hmc_group_id"),
    )

    id = Column(Integer, primary_key=True)
    hmc_group_id = Column(Integer, ForeignKey("hmc_groups.id", ondelete="CASCADE"), nullable=False)
    floor_id = Column(Integer, ForeignKey("hostel_floors.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    group = relationship("HMCGroup", back_populates="floor_assignments")
    floor = relationship("HostelFloor")
