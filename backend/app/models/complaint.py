
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.complaint_status_history import ComplaintStatusHistory
    from app.models.department import Department
    from app.models.user import User


class Complaint(Base):
    __tablename__ = "complaints"

    __table_args__ = (
        Index(
            "ix_complaints_created_by_id_created_at",
            "created_by_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)

    department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_by_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_complaints_created_by_id_users",
        ),
        nullable=False,
        index=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="submitted",
        index=True,
    )

    is_public = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    # Legacy text location fields
    hostel = Column(String(100), nullable=True)
    wing = Column(String(50), nullable=True)
    floor = Column(String(20), nullable=True)

    # Canonical verified location reference
    floor_id = Column(
        Integer,
        ForeignKey(
            "hostel_floors.id",
            ondelete="RESTRICT",
            name="fk_complaints_floor_id_hostel_floors",
        ),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    resolved_at = Column(DateTime(timezone=True), nullable=True)

    reopen_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # Relationships
    department = relationship(
        "Department",
        back_populates="complaints",
    )

    creator = relationship(
        "User",
        back_populates="complaints",
    )

    status_history = relationship(
        "ComplaintStatusHistory",
        back_populates="complaint",
        order_by="ComplaintStatusHistory.id",
        passive_deletes="all",
    )
