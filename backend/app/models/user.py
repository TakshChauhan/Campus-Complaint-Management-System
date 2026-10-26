from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.complaint import Complaint
    from app.models.oauth import UserExternalIdentity
    from app.models.verification_token import EmailVerificationToken


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'staff', 'admin')", name="ck_users_role"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="student", index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    email_verification_required = Column(Boolean, default=False, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    wing_id = Column(Integer, ForeignKey("wings.id", ondelete="SET NULL"), nullable=True, index=True)
    residence_building_id = Column(Integer, ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True, index=True)
    residence_floor_id = Column(Integer, ForeignKey("floors.id", ondelete="SET NULL"), nullable=True, index=True)
    residence_verified_at = Column(DateTime(timezone=True), nullable=True)
    residence_verified_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    department = relationship("Department", back_populates="staff_members")
    wing = relationship("Wing", back_populates="students", foreign_keys=[wing_id])
    residence_building = relationship("Building", foreign_keys=[residence_building_id])
    residence_floor = relationship("Floor", back_populates="students", foreign_keys=[residence_floor_id])
    residence_verified_by = relationship("User", foreign_keys=[residence_verified_by_id], remote_side=[id])
    # Complaint history is retained when a user record is removed: the database
    # foreign key is ON DELETE RESTRICT (migration 0004) and passive_deletes="all"
    # stops the ORM from cascading deletes or nulling created_by_id. Retire
    # accounts by setting is_active=False instead of deleting them.
    complaints = relationship("Complaint", back_populates="creator", passive_deletes="all", foreign_keys="Complaint.created_by_id")
    verification_tokens = relationship("EmailVerificationToken", back_populates="user", cascade="all, delete-orphan")
    external_identities = relationship("UserExternalIdentity", back_populates="user", cascade="all, delete-orphan")

    @property
    def google_linked(self) -> bool:
        """Returns True if user has an active Google external identity link."""
        if not self.external_identities:
            return False
        return any(identity.provider == "google" for identity in self.external_identities)
