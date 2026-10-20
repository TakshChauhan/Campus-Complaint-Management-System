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
from app.schemas.auth import GoogleLinkExchangeResponse, TokenResponse
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


def email_domain_allowed(email: str) -> bool:
    """True when the email's domain is in ALLOWED_EMAIL_DOMAINS (or the list is empty / '*')."""
    allowed = settings.ALLOWED_EMAIL_DOMAINS or []
    if not allowed or "*" in allowed:
        return True
    domain = email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""
    return any(domain == d or domain.endswith("." + d) for d in allowed)


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


def start_google_link(
    db: Session,
    user: User,
    origin: str,
    client_challenge: str,
) -> Dict[str, str]:
    """Initiates Google OIDC flow for account linking to an existing authenticated CCMS user."""
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

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    # Check if user already has a linked Google identity
    existing_ident = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.user_id == user.id,
        )
        .first()
    )
    if existing_ident:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Google account is already linked to your profile.",
        )

    # 1. Generate cryptographic tokens
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = calculate_pkce_challenge(code_verifier)

    # 2. Package linking payload and encrypt before DB persistence
    payload_dict = {
        "intent": "link",
        "user_id": user.id,
        "verifier": code_verifier,
    }
    code_verifier_encrypted = encrypt_secret(json.dumps(payload_dict))
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
        raise ValueError("Google ID token verification failed.")

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
            "An account already exists with this email. "
            "Sign in using your password, then connect Google from your account settings."
        )

    # 3. Institutional access policy for NEW accounts.
    # When no Google Workspace hosted-domain allowlist is configured, the signed
    # 'hd' claim is not checked, so apply the same institutional email-domain
    # policy used for password registration. Without this, any verified personal
    # Google account (e.g. @gmail.com) could self-provision a student account.
    if not settings.GOOGLE_ALLOWED_HOSTED_DOMAINS and not email_domain_allowed(normalized_email):
        domains_str = ", ".join(f"@{d}" for d in settings.ALLOWED_EMAIL_DOMAINS)
        raise ValueError(
            f"Google sign-in is limited to official university accounts ({domains_str})."
        )

    # 4. Create brand-new Student account
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


def link_google_identity_to_user(
    db: Session,
    user_id: int,
    sub: str,
    email: str,
) -> User:
    """
    Safely binds verified Google sub identity to an existing authenticated CCMS user.
    Validates user active status, canonical email match, and identity uniqueness.
    Preserves existing user ID, role, password hash, and complaints.
    """
    now = datetime.now(timezone.utc)
    normalized_google_email = email.strip().lower()

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise ValueError("User account is inactive or not found.")

    # Canonical email match verification
    normalized_user_email = user.email.strip().lower()
    if normalized_google_email != normalized_user_email:
        raise ValueError(
            f"The Google account email ({normalized_google_email}) does not match your CCMS account email ({normalized_user_email})."
        )

    # Check if Google sub is already linked to another CCMS user (Scenario D)
    existing_sub_ident = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.provider_user_id == sub,
        )
        .first()
    )
    if existing_sub_ident:
        if existing_sub_ident.user_id != user.id:
            raise ValueError("This Google account is already linked to another CCMS user.")
        # Already linked to this user, nothing more to do
        return user

    # Check if this user already has a different Google account linked
    existing_user_ident = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.user_id == user.id,
        )
        .first()
    )
    if existing_user_ident and existing_user_ident.provider_user_id != sub:
        raise ValueError("Your CCMS account is already linked to a different Google account.")

    # Bind the verified Google identity
    new_ident = UserExternalIdentity(
        user_id=user.id,
        provider="google",
        provider_user_id=sub,
        email=normalized_google_email,
        created_at=now,
    )
    db.add(new_ident)

    # Since Google OIDC verified ownership of this exact email address,
    # mark email_verified if it wasn't already.
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = now

    db.commit()
    db.refresh(user)
    return user


def render_callback_html(
    target_origin: Optional[str],
    success: bool,
    ticket: Optional[str] = None,
    error_message: Optional[str] = None,
    is_link_required: bool = False,
    is_linking: bool = False,
) -> str:
    """
    Renders a hardened, minimal HTML page with strict CSP and no-referrer headers.
    Communicates the handoff ticket or error via window.opener.postMessage strictly to target_origin.
    """
    nonce = secrets.token_hex(16)
    safe_target = html.escape(target_origin) if target_origin else ""
    safe_ticket = html.escape(ticket or "")
    safe_error = html.escape(error_message or "")

    msg_type = (
        ("CCMS_GOOGLE_LINK_SUCCESS" if is_linking else "CCMS_GOOGLE_AUTH_SUCCESS")
        if success
        else ("CCMS_GOOGLE_LINK_ERROR" if is_linking else "CCMS_GOOGLE_AUTH_ERROR")
    )

    payload = {
        "type": msg_type,
        "ticket": ticket if success else None,
        "error": error_message if not success else None,
        "link_required": is_link_required,
        "is_linking": is_linking,
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

    if is_linking:
        status_title = "Account Linking Complete" if success else "Account Linking Notice"
        display_body = (
            "Google account connected successfully! Closing window..."
            if success
            else f"<div class='error'>{safe_error}</div>"
        )
    else:
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
    encrypted_verifier = tx.code_verifier_encrypted

    # Atomic single-use consumption: a conditional DELETE whose rowcount tells us
    # whether *this* request won. Two concurrent callbacks carrying the same state
    # cannot both proceed (the earlier query-then-delete had a race window).
    consumed = (
        db.query(OAuthTransaction)
        .filter(OAuthTransaction.id == tx.id, OAuthTransaction.state_hash == state_h)
        .delete(synchronize_session=False)
    )
    db.commit()
    if consumed != 1:
        return render_callback_html(
            None,
            False,
            error_message="Authentication request has expired or was already used. Please try again.",
        )

    try:
        decrypted_raw = decrypt_secret(encrypted_verifier)
    except Exception:
        return render_callback_html(origin, False, error_message="Failed to decrypt transaction state.")

    intent = "login"
    linking_user_id = None
    try:
        parsed = json.loads(decrypted_raw)
        if isinstance(parsed, dict) and parsed.get("intent") == "link":
            intent = "link"
            linking_user_id = parsed.get("user_id")
            code_verifier = parsed.get("verifier", "")
        else:
            code_verifier = decrypted_raw
    except (json.JSONDecodeError, TypeError):
        code_verifier = decrypted_raw

    # 2. Exchange code for Google ID token
    try:
        tokens = exchange_code_with_google(code, code_verifier)
        id_token_str = tokens["id_token"]
        claims = verify_google_id_token(id_token_str, expected_nonce)
    except Exception as e:
        logger.warning("Google exchange or ID token validation failed: %s", str(e))
        return render_callback_html(origin, False, error_message=str(e), is_linking=(intent == "link"))

    sub = claims["sub"]
    email = claims["email"]
    name = claims.get("name")

    # 3. Handle linking flow vs login flow
    if intent == "link":
        try:
            user = link_google_identity_to_user(db=db, user_id=linking_user_id, sub=sub, email=email)
        except ValueError as e:
            return render_callback_html(origin, False, error_message=str(e), is_linking=True)
        except Exception as e:
            logger.exception("Unexpected error linking Google account")
            return render_callback_html(
                origin,
                False,
                error_message="A server error occurred while linking your account.",
                is_linking=True,
            )

        # Create short-lived single-use handoff ticket for linking confirmation
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

        return render_callback_html(origin, True, ticket=ticket, is_linking=True)

    # Regular login flow: Resolve internal CCMS user
    try:
        user, _ = resolve_or_create_user_for_google(db=db, sub=sub, email=email, name=name)
    except ValueError as e:
        err_msg = str(e)
        is_link_req = "sign in using your password" in err_msg.lower() or "account already exists" in err_msg.lower()
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

    # Atomic single-use consumption via conditional UPDATE: only one request can
    # flip consumed_at from NULL, so concurrent replays of the same ticket fail.
    consumed = (
        db.query(OAuthHandoffTicket)
        .filter(OAuthHandoffTicket.id == handoff.id, OAuthHandoffTicket.consumed_at.is_(None))
        .update({OAuthHandoffTicket.consumed_at: now}, synchronize_session=False)
    )
    db.commit()
    if consumed != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already redeemed authentication ticket.",
        )
    db.refresh(handoff)

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


def exchange_google_link_ticket(
    db: Session,
    ticket: str,
    client_verifier: str,
    origin: str,
    current_user_id: int,
) -> GoogleLinkExchangeResponse:
    """
    Exchanges single-use handoff ticket for account linking confirmation.
    Atomically consumes ticket, verifies origin, client PKCE verifier, and user ID match.
    """
    if not settings.GOOGLE_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not enabled.",
        )

    ticket_h = hash_token(ticket)
    now = datetime.now(timezone.utc)

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
            detail="Invalid, expired, or already redeemed linking ticket.",
        )

    # Prevent account switching or ticket theft: ticket must match the current authenticated user
    if handoff.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user does not match the linking ticket owner.",
        )

    # Atomic single-use consumption
    consumed = (
        db.query(OAuthHandoffTicket)
        .filter(OAuthHandoffTicket.id == handoff.id, OAuthHandoffTicket.consumed_at.is_(None))
        .update({OAuthHandoffTicket.consumed_at: now}, synchronize_session=False)
    )
    db.commit()
    if consumed != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already redeemed linking ticket.",
        )
    db.refresh(handoff)

    # Origin check
    normalized_req_origin = (origin or "").strip().rstrip("/")
    if handoff.origin != normalized_req_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin mismatch between linking start and ticket exchange.",
        )

    # Verify S256 PKCE challenge
    if not verify_pkce_challenge(client_verifier, handoff.client_challenge):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client verifier proof for linking ticket.",
        )

    # Re-fetch user
    user = db.query(User).filter(User.id == handoff.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive or not found.",
        )

    return GoogleLinkExchangeResponse(
        message="Google account connected successfully. You can now sign in using either Google or your password.",
        user=UserSafeResponse.model_validate(user),
    )


def get_google_link_status(db: Session, user: User) -> Dict[str, Any]:
    """Returns linking status and email for the current user."""
    identity = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.user_id == user.id,
        )
        .first()
    )
    return {
        "linked": identity is not None,
        "email": identity.email if identity else None,
    }


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
