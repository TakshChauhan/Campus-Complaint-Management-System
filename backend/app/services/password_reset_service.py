import logging
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import password_reset_rate_limiter
from app.core.security import get_password_hash, hash_token, verify_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.email_service import get_email_sender

logger = logging.getLogger("ccms.password_reset")


def request_password_reset(db: Session, email: str) -> None:
    """Process a password reset request.
    
    Enforces at most 3 requests per email per hour.
    Always returns without error to prevent user enumeration.
    Dispatches a single-use token valid for 30 minutes to registered, active accounts.
    """
    # Enforce rate limit (at most 3 per hour per email)
    password_reset_rate_limiter.check(email)

    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    # Neutral return if user doesn't exist or is deactivated (prevents enumeration)
    if not user or not user.is_active:
        logger.info("Password reset requested for unknown or inactive email")
        return

    now = datetime.now(timezone.utc)

    # Invalidate prior unused tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    # Generate single-use secure random token and store its SHA-256 hash
    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    expires_at = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()

    try:
        get_email_sender().send_password_reset_email(
            to_email=user.email,
            name=user.name,
            token=raw_token,
        )
        logger.info("Password reset email sent to user ID %s", user.id)
    except Exception as exc:
        logger.exception("Failed to dispatch password reset email for user %s: %s", user.id, str(exc))


def reset_password_with_token(db: Session, raw_token: str, new_password: str) -> None:
    """Verify single-use token and update user password hash.
    
    Atomically consumes token, voids other outstanding tokens, and hashes the new password.
    """
    token_h = hash_token(raw_token)
    token_record = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_h).first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    now = datetime.now(timezone.utc)

    if token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset token has already been used.",
        )

    token_exp = token_record.expires_at
    if token_exp.tzinfo is None:
        token_exp = token_exp.replace(tzinfo=timezone.utc)

    if token_exp <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset token has expired.",
        )

    # Atomically mark this token as consumed to prevent concurrent race conditions
    stmt = (
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == token_record.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    result = db.execute(stmt)

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset token has already been used.",
        )

    user = db.query(User).filter(User.id == token_record.user_id).first()
    if not user or not user.is_active:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account associated with this token is invalid or deactivated.",
        )

    # Update password using existing bcrypt hash utility
    user.password_hash = get_password_hash(new_password)

    # Invalidate any other outstanding reset tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    db.commit()
    logger.info("Password successfully reset for user ID %s", user.id)


def change_current_user_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    """Change password for an authenticated user.
    
    Verifies current password and ensures new password differs.
    """
    if user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account does not have a local password configured.",
        )

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password.",
        )

    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password.",
        )

    user.password_hash = get_password_hash(new_password)

    # Invalidate any outstanding reset tokens
    now = datetime.now(timezone.utc)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    db.commit()
    logger.info("Password successfully changed for user ID %s", user.id)
