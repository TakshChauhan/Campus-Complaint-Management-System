from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserExternalIdentity(Base):
    """External identity mapping for single sign-on providers (e.g. Google OAuth/OIDC)."""
    __tablename__ = "user_external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_external_identities_provider_sub"),
        UniqueConstraint("user_id", "provider", name="uq_external_identities_user_provider"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="google")
    provider_user_id = Column(String(255), nullable=False, index=True)  # Provider 'sub' claim
    email = Column(String(255), nullable=True)  # Provider email reported at link time
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship to internal CCMS user
    user = relationship("User", back_populates="external_identities")


class OAuthTransaction(Base):
    """Database-backed short-lived state and PKCE transaction record for OAuth login."""
    __tablename__ = "oauth_transactions"

    id = Column(Integer, primary_key=True, index=True)
    state_hash = Column(String(64), unique=True, index=True, nullable=False)  # SHA-256 of random state
    nonce = Column(String(128), nullable=False)
    code_verifier_encrypted = Column(String(512), nullable=False)  # Encrypted Google PKCE verifier
    origin = Column(String(255), nullable=False)  # Verified initiating frontend Origin
    client_challenge = Column(String(128), nullable=False)  # Frontend S256 challenge for handoff
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OAuthHandoffTicket(Base):
    """Database-backed single-use opaque handoff ticket bound to frontend origin and challenge."""
    __tablename__ = "oauth_handoff_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_hash = Column(String(64), unique=True, index=True, nullable=False)  # SHA-256 of opaque ticket
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_challenge = Column(String(128), nullable=False)  # Must match challenge from start
    origin = Column(String(255), nullable=False)  # Exact frontend origin
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)  # Null until atomically consumed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")
