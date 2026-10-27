"""Hostel cluster in the campus residence hierarchy."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, UniqueConstraint, func, true
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Hostel(Base):
    __tablename__ = "hostels"
    __table_args__ = (
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostels_code_canonical"),
        CheckConstraint("length(trim(name)) > 0", name="ck_hostels_name_nonempty"),
        UniqueConstraint("code", name="uq_hostels_code"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    wings = relationship("HostelWing", back_populates="hostel", passive_deletes="all")
