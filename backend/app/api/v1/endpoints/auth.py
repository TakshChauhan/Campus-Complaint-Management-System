from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.rate_limit import auth_rate_limiter
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthStartRequest,
    GoogleAuthStartResponse,
    GoogleExchangeRequest,
    GoogleLinkExchangeResponse,
    GoogleLinkStatusResponse,
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.schemas.user import UserSafeResponse
from app.services.auth_service import (
    authenticate_user,
    register_student,
    resend_verification_email,
    verify_email_token,
)
from app.services.google_auth_service import (
    exchange_google_link_ticket,
    exchange_google_ticket,
    get_google_link_status,
    handle_google_callback,
    start_google_auth,
    start_google_link,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserSafeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student account",
    description="Registers a new student account with default 'student' role. Returns safe profile information upon successful creation.",
    responses={
        201: {"description": "Student successfully registered"},
        400: {"description": "Validation error or invalid input format"},
        409: {"description": "An account with this email address already exists"},
        429: {"description": "Too many requests. Rate limit exceeded"},
        502: {"description": "Account created, but verification email could not be delivered"},
    },
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> UserSafeResponse:
    auth_rate_limiter.check(request)
    user = register_student(db=db, reg_in=payload)
    resp = UserSafeResponse.model_validate(user)
    resp.message = "Your account has been created. Please verify your email before signing in."
    return resp


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify student email address using single-use token",
    description="Atomically consumes the verification token and sets email_verified=True without issuing a JWT.",
    responses={
        200: {"description": "Email verified successfully"},
        400: {"description": "Invalid, expired, or previously consumed token"},
        429: {"description": "Too many requests. Rate limit exceeded"},
    },
)
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> VerifyEmailResponse:
    auth_rate_limiter.check(request)
    user = verify_email_token(db=db, raw_token=payload.token)
    return VerifyEmailResponse(
        message="Your email address has been verified successfully. You may now sign in.",
        email=user.email,
    )


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend student account email verification link",
    description="Generates a fresh token, invalidates prior unused tokens, and dispatches a new verification email. Returns neutral response to protect privacy.",
    responses={
        200: {"description": "Verification request processed"},
        429: {"description": "Too many requests. Rate limit exceeded"},
        502: {"description": "Failed to deliver verification email"},
    },
)
def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ResendVerificationResponse:
    auth_rate_limiter.check(request)
    resend_verification_email(db=db, email=payload.email)
    return ResendVerificationResponse()



@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain JWT bearer token",
    description="Authenticates student, staff, or admin credentials. Returns a signed JWT access token and safe user details.",
    responses={
        200: {"description": "Authentication successful"},
        401: {"description": "Invalid email or password"},
        403: {"description": "Account is inactive"},
        429: {"description": "Too many requests. Rate limit exceeded"},
    },
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    auth_rate_limiter.check(request)
    return authenticate_user(db=db, login_in=payload)


@router.post(
    "/google/start",
    response_model=GoogleAuthStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate Google OAuth 2.0 PKCE authentication flow",
    description="Generates short-lived transaction state and returns the Google OAuth authorization URL for popup sign-in.",
    responses={
        200: {"description": "Google authorization URL generated successfully"},
        400: {"description": "Invalid input format"},
        403: {"description": "Request origin not permitted"},
        503: {"description": "Google authentication is not enabled"},
    },
)
def google_auth_start(
    payload: GoogleAuthStartRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> GoogleAuthStartResponse:
    auth_rate_limiter.check(request)
    origin = request.headers.get("origin") or request.headers.get("referer", "").split("/api")[0]
    result = start_google_auth(
        db=db,
        origin=origin,
        client_challenge=payload.client_challenge,
    )
    return GoogleAuthStartResponse(**result)


@router.get(
    "/google/callback",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Google OAuth 2.0 callback endpoint",
    description="Receives authorization code from Google, validates state, and returns a secure HTML postMessage handoff page.",
)
def google_auth_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Google authorization code"),
    state: Optional[str] = Query(None, description="OAuth transaction state token"),
    error: Optional[str] = Query(None, description="Google authorization error, if any"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    # Security: Query parameters containing sensitive OAuth code/state are NOT logged
    html_content = handle_google_callback(
        db=db,
        code=code,
        state=state,
        error=error,
    )
    return HTMLResponse(
        content=html_content,
        status_code=status.HTTP_200_OK,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/google/exchange",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange single-use handoff ticket for CCMS JWT token",
    description="Atomically consumes the handoff ticket, verifies client PKCE verifier proof, and issues the authenticated JWT.",
    responses={
        200: {"description": "Handoff ticket redeemed successfully, returning JWT"},
        400: {"description": "Invalid, expired, or replayed ticket or verifier proof"},
        403: {"description": "Origin mismatch or deactivated user account"},
        503: {"description": "Google authentication is not enabled"},
    },
)
def google_auth_exchange(
    payload: GoogleExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    auth_rate_limiter.check(request)
    origin = request.headers.get("origin") or ""
    return exchange_google_ticket(
        db=db,
        ticket=payload.ticket,
        client_verifier=payload.client_verifier,
        origin=origin,
    )


@router.post(
    "/google/link/start",
    response_model=GoogleAuthStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate Google account linking flow for authenticated user",
    description="Generates short-lived state bound to the authenticated user and returns Google authorization URL for linking.",
    responses={
        200: {"description": "Google linking authorization URL generated successfully"},
        400: {"description": "A Google account is already linked or invalid input"},
        401: {"description": "Authentication required"},
        403: {"description": "Request origin not permitted or inactive account"},
        503: {"description": "Google authentication is not enabled"},
    },
)
def google_link_start(
    payload: GoogleAuthStartRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoogleAuthStartResponse:
    auth_rate_limiter.check(request)
    origin = request.headers.get("origin") or request.headers.get("referer", "").split("/api")[0]
    result = start_google_link(
        db=db,
        user=current_user,
        origin=origin,
        client_challenge=payload.client_challenge,
    )
    return GoogleAuthStartResponse(**result)


@router.post(
    "/google/link/exchange",
    response_model=GoogleLinkExchangeResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange single-use ticket for Google account linking confirmation",
    description="Validates linking ticket, matches authenticated session, verifies PKCE challenge, and confirms linking.",
    responses={
        200: {"description": "Google account linked successfully"},
        400: {"description": "Invalid, expired, or replayed ticket or PKCE verifier"},
        401: {"description": "Authentication required"},
        403: {"description": "Account mismatch, inactive user, or origin mismatch"},
        503: {"description": "Google authentication is not enabled"},
    },
)
def google_link_exchange(
    payload: GoogleExchangeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoogleLinkExchangeResponse:
    auth_rate_limiter.check(request)
    origin = request.headers.get("origin") or ""
    return exchange_google_link_ticket(
        db=db,
        ticket=payload.ticket,
        client_verifier=payload.client_verifier,
        origin=origin,
        current_user_id=current_user.id,
    )


@router.get(
    "/google/status",
    response_model=GoogleLinkStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check current user's Google account linking status",
    description="Returns whether the authenticated user has a linked Google account.",
    responses={
        200: {"description": "Linking status retrieved successfully"},
        401: {"description": "Authentication required"},
    },
)
def google_link_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoogleLinkStatusResponse:
    result = get_google_link_status(db=db, user=current_user)
    return GoogleLinkStatusResponse(**result)
