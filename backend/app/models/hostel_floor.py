"""A floor within one hostel wing."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, true
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class HostelFloor(Base):
    __tablename__ = "hostel_floors"
    __table_args__ = (
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostel_floors_code_canonical"),
        CheckConstraint("length(trim(name)) > 0", name="ck_hostel_floors_name_nonempty"),
        UniqueConstraint("wing_id", "code", name="uq_hostel_floors_wing_code"),
        Index("ix_hostel_floors_wing_id", "wing_id"),
    )

    id = Column(Integer, primary_key=True)
    wing_id = Column(Integer, ForeignKey("hostel_wings.id", ondelete="RESTRICT"), nullable=False)
    code = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    wing = relationship("HostelWing", back_populates="floors")
