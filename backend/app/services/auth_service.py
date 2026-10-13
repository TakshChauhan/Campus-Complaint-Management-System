import logging
from datetime import timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import sqlalchemy

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserSafeResponse

logger = logging.getLogger("ccms.auth_service")

# Pre-computed module-level dummy bcrypt hash to mitigate login timing differences on nonexistent accounts
DUMMY_BCRYPT_HASH = "$2b$12$lM.oL1GhgGx5KXECRb3Iz.QswNA0pEahU1pl1UrAoVgQVyVgdiXg6"


def register_student(db: Session, reg_in: RegisterRequest) -> User:
    """Register a new student account. Strictly assigns role='student' and unverified email."""
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
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except sqlalchemy.exc.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    except Exception:
        logger.exception("Unexpected error during student registration")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user due to a database error.",
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
