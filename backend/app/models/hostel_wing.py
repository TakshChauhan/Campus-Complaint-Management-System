"""A wing is one physical building within a hostel cluster."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, true
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class HostelWing(Base):
    __tablename__ = "hostel_wings"
    __table_args__ = (
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostel_wings_code_canonical"),
        CheckConstraint("length(trim(name)) > 0", name="ck_hostel_wings_name_nonempty"),
        UniqueConstraint("code", name="uq_hostel_wings_code"),
        Index("ix_hostel_wings_hostel_id", "hostel_id"),
    )

    id = Column(Integer, primary_key=True)
    hostel_id = Column(Integer, ForeignKey("hostels.id", ondelete="RESTRICT"), nullable=False)
    code = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    hostel = relationship("Hostel", back_populates="wings")
    floors = relationship("HostelFloor", back_populates="wing", passive_deletes="all")
