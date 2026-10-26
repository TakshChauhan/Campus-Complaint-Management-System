"""A wing is a building-level entity and may span many floors."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Wing(Base):
    __tablename__ = "wings"
    __table_args__ = (UniqueConstraint("building_id", "name", name="uq_wings_building_name"),)

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    building = relationship("Building", back_populates="wings")
    students = relationship("User", back_populates="wing", foreign_keys="User.wing_id")
    hmc_memberships = relationship("HMCGroupWing", back_populates="wing")
