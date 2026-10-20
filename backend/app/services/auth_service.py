from datetime import datetime, timedelta, timezone
import logging
import secrets
from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session
import sqlalchemy

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, hash_token, verify_password
from app.models.user import User
from app.models.verification_token import EmailVerificationToken
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserSafeResponse
from app.services.email_service import EmailDeliveryError, get_email_sender

logger = logging.getLogger("ccms.auth_service")

# Pre-computed module-level dummy bcrypt hash to mitigate login timing differences on nonexistent accounts
DUMMY_BCRYPT_HASH = "$2b$12$lM.oL1GhgGx5KXECRb3Iz.QswNA0pEahU1pl1UrAoVgQVyVgdiXg6"


def register_student(db: Session, reg_in: RegisterRequest) -> User:
    """
    Register a new student account. Strictly assigns role='student', email_verification_required=True,
    and unverified email. Generates and securely stores a hashed verification token and dispatches
    the verification email.
    """
    normalized_email = reg_in.email.strip().lower()

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    hashed_pw = get_password_hash(reg_in.password)
    user = User(
        name=reg_in.name.strip(),
        email=normalized_email,
        password_hash=hashed_pw,
        role="student",
        is_active=True,
        email_verified=False,
        email_verified_at=None,
        email_verification_required=True,
    )
    db.add(user)
    try:
        db.flush()
    except sqlalchemy.exc.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    except Exception:
        logger.exception("Unexpected error during student user flush")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user due to a database error.",
        )

    # Generate single-use random verification token
    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES)

    verification_token = EmailVerificationToken(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
    )
    db.add(verification_token)

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        logger.exception("Failed to commit student registration and token")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user due to a database commit error.",
        )

    # Dispatch verification email
    try:
        get_email_sender().send_verification_email(
            to_email=user.email,
            name=user.name,
            token=raw_token,
        )
    except EmailDeliveryError as exc:
        logger.error("Failed to deliver registration verification email: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Account created, but verification email could not be delivered. Please try resending verification.",
        )
    except Exception as exc:
        logger.exception("Unexpected error sending registration verification email: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Account created, but verification email could not be delivered. Please try resending verification.",
        )

    return user


def authenticate_user(db: Session, login_in: LoginRequest) -> TokenResponse:
    """Verify credentials and issue bearer JWT. Does not leak email existence or passwordless status."""
    normalized_email = login_in.email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    invalid_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not user:
        # Mitigate account-enumeration timing differences by exercising bcrypt verification
        verify_password(login_in.password, DUMMY_BCRYPT_HASH)
        raise invalid_credentials_exception

    if user.password_hash is None:
        # Users registered solely via Google OAuth without a local password cannot authenticate with password
        verify_password(login_in.password, DUMMY_BCRYPT_HASH)
        raise invalid_credentials_exception

    if not verify_password(login_in.password, user.password_hash):
        raise invalid_credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact system administrator.",
        )

    # Enforce email verification for accounts requiring it (backward-compatible with legacy accounts)
    if getattr(user, "email_verification_required", False) and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your email address has not been verified. Please check your inbox for the verification link.",
        )

    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        subject=str(user.id),
        claims={
            "role": user.role,
        },
        expires_delta=expires_delta,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSafeResponse.model_validate(user),
    )


def verify_email_token(db: Session, raw_token: str) -> User:
    """
    Atomically validates and consumes email verification token, setting email_verified=True.
    Rejects missing, expired, or previously consumed tokens safely.
    """
    if not raw_token or not raw_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is required.",
        )

    token_h = hash_token(raw_token.strip())
    now = datetime.now(timezone.utc)

    # 1. Inspect token state
    token_record = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_h)
        .first()
    )
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification link.",
        )

    if token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used.",
        )

    token_exp = token_record.expires_at
    if token_exp.tzinfo is None:
        token_exp = token_exp.replace(tzinfo=timezone.utc)

    if token_exp <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired. Please request a new verification email.",
        )

    # 2. Atomic conditional consumption: UPDATE ... WHERE token_hash = :h AND used_at IS NULL AND expires_at > :now
    stmt = (
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash == token_h,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    result = db.execute(stmt)

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used or expired.",
        )

    # 3. Mark user verified in the same transaction
    user = db.query(User).filter(User.id == token_record.user_id).first()
    if not user:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account associated with this verification link was not found.",
        )

    user.email_verified = True
    user.email_verified_at = now
    db.commit()
    db.refresh(user)
    return user


def resend_verification_email(db: Session, email: str) -> None:
    """
    Invalidates prior unused tokens and generates/sends a fresh token.
    Returns neutral response without disclosing whether email exists or is verified.
    """
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    # Neutral return if user doesn't exist, is inactive, or doesn't need verification
    if (
        not user
        or not user.is_active
        or not getattr(user, "email_verification_required", False)
        or user.email_verified
    ):
        return

    now = datetime.now(timezone.utc)

    # Invalidate prior unused tokens
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)


    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES)

    new_token = EmailVerificationToken(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
    )
    db.add(new_token)
    db.commit()

    try:
        get_email_sender().send_verification_email(
            to_email=user.email,
            name=user.name,
            token=raw_token,
        )
    except EmailDeliveryError as exc:
        logger.error("Failed to resend verification email: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver verification email. Please try again later.",
        )
    except Exception as exc:
        logger.exception("Unexpected error during resend verification email: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver verification email. Please try again later.",
        )
