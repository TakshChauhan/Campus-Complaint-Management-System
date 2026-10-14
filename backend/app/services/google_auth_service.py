import base64
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from fastapi import HTTPException, status
import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    calculate_pkce_challenge,
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_token,
    verify_pkce_challenge,
)
from app.models.oauth import OAuthHandoffTicket, OAuthTransaction, UserExternalIdentity
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserSafeResponse

logger = logging.getLogger("ccms.google_auth")

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_VALID_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]

# In-memory JWK client cache with 1-hour lifespan
_jwk_client: Optional[PyJWKClient] = None


def get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True, lifespan=3600)
    return _jwk_client


def set_jwk_client_for_testing(client: Optional[PyJWKClient]) -> None:
    """Allow injecting mock JWK client during automated test suites."""
    global _jwk_client
    _jwk_client = client


def check_origin_allowed(origin: Optional[str]) -> bool:
    """Validate that the requesting origin matches configured CORS origins."""
    if not origin:
        return False
    normalized = origin.strip().rstrip("/")
    allowed = [str(o).strip().rstrip("/") for o in settings.CORS_ORIGINS]
    return normalized in allowed or "*" in allowed


def start_google_auth(db: Session, origin: str, client_challenge: str) -> Dict[str, str]:
    """Initiates Google OIDC flow: generates state, nonce, PKCE, records transaction, returns auth URL."""
    if not settings.GOOGLE_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In is not enabled on this server.",
        )

    if not check_origin_allowed(origin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Origin '{origin}' is not permitted for authentication handoff.",
        )

    # 1. Generate cryptographic tokens
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    # PKCE verifier (43-128 chars urlsafe)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = calculate_pkce_challenge(code_verifier)

    # 2. Encrypt sensitive PKCE verifier before DB persistence
    code_verifier_encrypted = encrypt_secret(code_verifier)
    state_h = hash_token(state)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.GOOGLE_OAUTH_STATE_EXPIRE_SECONDS)

    # 3. Store transaction state in database
    tx = OAuthTransaction(
        state_hash=state_h,
        nonce=nonce,
        code_verifier_encrypted=code_verifier_encrypted,
        origin=origin.strip().rstrip("/"),
        client_challenge=client_challenge.strip(),
        expires_at=expires_at,
    )
    db.add(tx)
    db.commit()

    # 4. Construct Google Authorization URL
    auth_params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    # If a single hosted domain is configured, suggest it to Google via hd param
    if len(settings.GOOGLE_ALLOWED_HOSTED_DOMAINS) == 1:
        auth_params["hd"] = settings.GOOGLE_ALLOWED_HOSTED_DOMAINS[0]

    auth_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(auth_params)}"
    return {
        "authorization_url": auth_url,
        "state": state,
    }


def verify_google_id_token(id_token_str: str, expected_nonce: str) -> Dict[str, Any]:
    """Validates Google ID Token cryptographic signature, issuer, audience, azp, exp, nonce, and claims."""
    try:
        jwks_client = get_jwk_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token_str)
        key = signing_key.key
    except Exception as e:
        logger.warning("Failed to retrieve signing key for Google ID token: %s", str(e))
        raise ValueError("Invalid Google ID token signature key.")

    try:
        # Decode and verify RS256 signature
        claims = jwt.decode(
            id_token_str,
            key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_OAUTH_CLIENT_ID,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iat": True,
                "verify_exp": True,
                "require": ["sub", "iss", "aud", "exp", "iat"],
            },
            leeway=60,  # 60s clock skew tolerance
        )
    except jwt.PyJWTError as e:
        logger.warning("Google ID token decoding/verification rejected: %s", str(e))
        raise ValueError(f"Google ID token verification failed: {str(e)}")

    # 1. Issuer verification (strict)
    iss = claims.get("iss")
    if iss not in GOOGLE_VALID_ISSUERS:
        raise ValueError(f"Invalid token issuer: '{iss}'. Expected Google issuer.")

    # 2. Authorized Party (azp) verification
    azp = claims.get("azp")
    if azp and azp != settings.GOOGLE_OAUTH_CLIENT_ID:
        raise ValueError(f"Invalid authorized party 'azp': '{azp}'. Does not match client ID.")

    # 3. Nonce verification
    token_nonce = claims.get("nonce")
    if not token_nonce or token_nonce != expected_nonce:
        raise ValueError("ID token nonce does not match transaction nonce.")

    # 4. Subject verification
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str) or not sub.strip():
        raise ValueError("Missing or invalid Google user subject 'sub'.")

    # 5. Email claim verification
    email = claims.get("email")
    if not email or not isinstance(email, str) or "@" not in email:
        raise ValueError("Missing or malformed email claim in Google token.")

    # 6. Explicit Boolean email_verified verification
    email_verified = claims.get("email_verified")
    if email_verified is not True:
        raise ValueError("Google account email is not verified (email_verified must be boolean True).")

    # 7. Hosted domain restriction (hd claim)
    allowed_domains = settings.GOOGLE_ALLOWED_HOSTED_DOMAINS
    if allowed_domains:
        token_hd = claims.get("hd")
        if not token_hd or str(token_hd).strip().lower() not in allowed_domains:
            domains_str = ", ".join(f"@{d}" for d in allowed_domains)
            raise ValueError(f"Google account domain is not authorized. Access restricted to: {domains_str}")

    return claims


def exchange_code_with_google(code: str, code_verifier: str) -> Dict[str, Any]:
    """Exchanges Google authorization code for tokens using time-bounded POST request."""
    data = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(GOOGLE_TOKEN_URL, data=data)
            if resp.status_code != 200:
                logger.warning("Google token endpoint returned error status %d", resp.status_code)
                raise ValueError("Failed to exchange authorization code with Google.")
            token_json = resp.json()
    except httpx.RequestError as e:
        logger.error("Network error communicating with Google token endpoint: %s", str(e))
        raise ValueError("Unable to reach Google authorization server.")

    if "id_token" not in token_json:
        raise ValueError("Google token response did not contain an id_token.")
    return token_json


def resolve_or_create_user_for_google(
    db: Session,
    sub: str,
    email: str,
    name: Optional[str],
) -> Tuple[User, bool]:
    """
    Safely resolves or creates internal CCMS user for Google identity.
    Returns: (user, is_new_account)
    Raises ValueError on account linking conflicts or inactive accounts.
    """
    normalized_email = email.strip().lower()

    # 1. Check existing external identity mapping for this Google subject
    existing_identity = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.provider_user_id == sub,
        )
        .first()
    )

    if existing_identity:
        user = existing_identity.user
        if not user or not user.is_active:
            raise ValueError("This account is currently deactivated. Please contact an administrator.")
        # Preserve user, role, and ID. Do NOT overwrite email if provider reported a different one.
        return user, False

    # 2. If no identity link, check if a CCMS user already exists with this email address
    existing_user_by_email = db.query(User).filter(User.email == normalized_email).first()
    if existing_user_by_email:
        # STRICT REQUIREMENT: Never auto-link an existing password account by email alone.
        # Direct user to existing password login.
        raise ValueError(
            "An account with this email address already exists. "
            "Please sign in with your email and password. "
            "Contact your administrator for account linking."
        )

    # 3. Create brand-new Student account
    now = datetime.now(timezone.utc)
    user_name = (name or normalized_email.split("@")[0]).strip()
    if len(user_name) < 2:
        user_name = "Campus Student"

    new_user = User(
        name=user_name,
        email=normalized_email,
        password_hash=None,  # Google-only users have NULL password_hash
        role="student",      # Strictly student role for new external users
        is_active=True,
        email_verified=True,  # Validated by Google OIDC claim
        email_verified_at=now,
    )
    db.add(new_user)
    db.flush()  # Obtain new_user.id

    identity = UserExternalIdentity(
        user_id=new_user.id,
        provider="google",
        provider_user_id=sub,
        email=normalized_email,
        created_at=now,
    )
    db.add(identity)
    db.commit()
    db.refresh(new_user)
    return new_user, True


def render_callback_html(
    target_origin: Optional[str],
    success: bool,
    ticket: Optional[str] = None,
    error_message: Optional[str] = None,
    is_link_required: bool = False,
) -> str:
    """
    Renders a hardened, minimal HTML page with strict CSP and no-referrer headers.
    Communicates the handoff ticket or error via window.opener.postMessage strictly to target_origin.
    """
    nonce = secrets.token_hex(16)
    safe_target = html.escape(target_origin) if target_origin else ""
    safe_ticket = html.escape(ticket or "")
    safe_error = html.escape(error_message or "")

    payload = {
        "type": "CCMS_GOOGLE_AUTH_SUCCESS" if success else "CCMS_GOOGLE_AUTH_ERROR",
        "ticket": ticket if success else None,
        "error": error_message if not success else None,
        "link_required": is_link_required,
    }
    payload_json = json.dumps(payload)

    # If target origin is unknown (e.g. invalid state), we must NEVER postMessage
    script_content = ""
    if target_origin:
        script_content = f"""
        (function() {{
            try {{
                if (window.opener && window.opener !== window) {{
                    window.opener.postMessage({payload_json}, {json.dumps(target_origin)});
                    setTimeout(function() {{ window.close(); }}, 300);
                }}
            }} catch (e) {{
                console.error("postMessage error:", e);
            }}
        }})();
        """

    status_title = "Authentication Complete" if success else "Authentication Notice"
    display_body = (
        "Sign-in successful! Closing window..."
        if success
        else f"<div class='error'>{safe_error}</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{status_title}</title>
    <meta name="referrer" content="no-referrer">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline';">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            background: #f8fafc;
            color: #1e293b;
            text-align: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            padding: 28px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            max-width: 420px;
            width: 100%;
        }}
        .error {{
            color: #b91c1c;
            font-size: 14px;
            margin: 12px 0;
            background: #fef2f2;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #fecaca;
        }}
        .hint {{
            font-size: 13px;
            color: #64748b;
            margin-top: 14px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h3>{status_title}</h3>
        <div>{display_body}</div>
        <p class="hint">You may close this window.</p>
    </div>
    {f'<script nonce="{nonce}">{script_content}</script>' if script_content else ''}
</body>
</html>"""


def handle_google_callback(
    db: Session,
    code: Optional[str],
    state: Optional[str],
    error: Optional[str],
) -> str:
    """
    Handles callback from Google: validates and atomically consumes state,
    exchanges code, resolves user, creates ticket, and returns secure postMessage HTML.
    """
    if not settings.GOOGLE_AUTH_ENABLED:
        return render_callback_html(None, False, error_message="Google authentication is disabled.")

    if error:
        return render_callback_html(None, False, error_message=f"Google authentication was cancelled: {error}")

    if not state or not code:
        return render_callback_html(None, False, error_message="Missing authorization code or state token.")

    state_h = hash_token(state)
    now = datetime.now(timezone.utc)

    # 1. Atomically retrieve and delete transaction state
    tx = (
        db.query(OAuthTransaction)
        .filter(
            OAuthTransaction.state_hash == state_h,
            OAuthTransaction.expires_at > now,
        )
        .first()
    )

    if not tx:
        # Replay, expired, or bogus state: do not send to unknown origin
        return render_callback_html(
            None,
            False,
            error_message="Authentication request has expired or was already used. Please try again.",
        )

    origin = tx.origin
    expected_nonce = tx.nonce
    client_challenge = tx.client_challenge

    try:
        code_verifier = decrypt_secret(tx.code_verifier_encrypted)
    except Exception:
        db.delete(tx)
        db.commit()
        return render_callback_html(origin, False, error_message="Failed to decrypt transaction state.")

    # Delete transaction to prevent any replay
    db.delete(tx)
    db.commit()

    # 2. Exchange code for Google ID token
    try:
        tokens = exchange_code_with_google(code, code_verifier)
        id_token_str = tokens["id_token"]
        claims = verify_google_id_token(id_token_str, expected_nonce)
    except Exception as e:
        logger.warning("Google exchange or ID token validation failed: %s", str(e))
        return render_callback_html(origin, False, error_message=str(e))

    sub = claims["sub"]
    email = claims["email"]
    name = claims.get("name")

    # 3. Resolve internal CCMS user
    try:
        user, _ = resolve_or_create_user_for_google(db=db, sub=sub, email=email, name=name)
    except ValueError as e:
        err_msg = str(e)
        is_link_req = "sign in with your email and password" in err_msg.lower()
        return render_callback_html(
            origin,
            False,
            error_message=err_msg,
            is_link_required=is_link_req,
        )
    except Exception as e:
        logger.exception("Unexpected error resolving user for Google sign in")
        return render_callback_html(
            origin,
            False,
            error_message="A server error occurred while resolving your account.",
        )

    # 4. Create short-lived single-use handoff ticket
    ticket = secrets.token_urlsafe(32)
    ticket_h = hash_token(ticket)
    ticket_expires_at = now + timedelta(seconds=settings.GOOGLE_OAUTH_TICKET_EXPIRE_SECONDS)

    handoff = OAuthHandoffTicket(
        ticket_hash=ticket_h,
        user_id=user.id,
        client_challenge=client_challenge,
        origin=origin,
        expires_at=ticket_expires_at,
        consumed_at=None,
    )
    db.add(handoff)
    db.commit()

    return render_callback_html(origin, True, ticket=ticket)


def exchange_google_ticket(
    db: Session,
    ticket: str,
    client_verifier: str,
    origin: str,
) -> TokenResponse:
    """
    Exchanges one-time handoff ticket with client verifier proof.
    Validates origin, verifies S256 challenge, atomically consumes ticket, issues CCMS TokenResponse.
    """
    if not settings.GOOGLE_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not enabled.",
        )

    ticket_h = hash_token(ticket)
    now = datetime.now(timezone.utc)

    # 1. Atomically query unconsumed, non-expired ticket
    handoff = (
        db.query(OAuthHandoffTicket)
        .filter(
            OAuthHandoffTicket.ticket_hash == ticket_h,
            OAuthHandoffTicket.consumed_at.is_(None),
            OAuthHandoffTicket.expires_at > now,
        )
        .first()
    )

    if not handoff:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already redeemed authentication ticket.",
        )

    # Mark consumed immediately to prevent replay
    handoff.consumed_at = now
    db.commit()

    # 2. Check Origin match
    normalized_req_origin = (origin or "").strip().rstrip("/")
    if handoff.origin != normalized_req_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin mismatch between authorization start and ticket exchange.",
        )

    # 3. Verify S256 PKCE challenge against client verifier
    if not verify_pkce_challenge(client_verifier, handoff.client_challenge):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client verifier proof for handoff ticket.",
        )

    # 4. Fetch and recheck user status
    user = db.query(User).filter(User.id == handoff.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive or not found.",
        )

    # 5. Issue CCMS JWT TokenResponse
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


def cleanup_expired_oauth_transactions(db: Session) -> int:
    """Removes expired transactions and old tickets from database."""
    now = datetime.now(timezone.utc)
    deleted_tx = (
        db.query(OAuthTransaction)
        .filter(OAuthTransaction.expires_at < now)
        .delete(synchronize_session=False)
    )
    deleted_tickets = (
        db.query(OAuthHandoffTicket)
        .filter(
            or_(
                OAuthHandoffTicket.expires_at < now,
                OAuthHandoffTicket.consumed_at.is_not(None),
            )
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted_tx + deleted_tickets
