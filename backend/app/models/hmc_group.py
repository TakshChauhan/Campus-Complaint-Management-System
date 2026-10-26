"""HMC groups and the building/floor-specific wings they manage."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class HMCGroup(Base):
    __tablename__ = "hmc_groups"
    __table_args__ = (UniqueConstraint("name", name="uq_hmc_groups_name"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    floor_id = Column(Integer, ForeignKey("floors.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    building = relationship("Building", back_populates="hmc_groups")
    floor = relationship("Floor", back_populates="hmc_groups")
    wing_assignments = relationship("HMCGroupWing", back_populates="group", cascade="all, delete-orphan")
    moderators = relationship("HMCGroupModerator", back_populates="group", cascade="all, delete-orphan")


class HMCGroupWing(Base):
    """Maps a building-level wing to one group for a particular floor."""
    __tablename__ = "hmc_group_wings"
    __table_args__ = (
        UniqueConstraint("building_id", "floor_id", "wing_id", name="uq_hmc_group_wings_location"),
        UniqueConstraint("hmc_group_id", "wing_id", name="uq_hmc_group_wings_group_wing"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hmc_group_id = Column(Integer, ForeignKey("hmc_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    floor_id = Column(Integer, ForeignKey("floors.id", ondelete="RESTRICT"), nullable=False, index=True)
    wing_id = Column(Integer, ForeignKey("wings.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    group = relationship("HMCGroup", back_populates="wing_assignments")
    building = relationship("Building")
    floor = relationship("Floor")
    wing = relationship("Wing", back_populates="hmc_memberships")
