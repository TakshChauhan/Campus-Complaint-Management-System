"""A numbered floor within a configured building."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("building_id", "name", name="uq_floors_building_name"),)

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    building = relationship("Building", back_populates="floors")
    hmc_groups = relationship("HMCGroup", back_populates="floor")
    students = relationship("User", back_populates="residence_floor", foreign_keys="User.residence_floor_id")
