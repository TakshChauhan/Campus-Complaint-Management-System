"""Configured hostel/building locations used for residence verification and HMC feeds."""
from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship
from app.db.base_class import Base


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("name", name="uq_buildings_name"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    floors = relationship("Floor", back_populates="building")
    wings = relationship("Wing", back_populates="building")
    hmc_groups = relationship("HMCGroup", back_populates="building")
