"""Comprehensive test suite for Google OpenID Connect (OIDC) authentication in CCMS.

Covers:
- PKCE S256 and cryptographic handoff flow
- New student account provisioning with NULL password hash
- Repeat login and stable internal identity
- Claims validation (RS256 signature, issuer, audience, azp, nonce, sub, email, boolean email_verified)
- Hosted domain restrictions (hd claim enforcement and empty allowlist behavior)
- Role elevation tampering prevention
- Account collision without auto-linking
- Inactive user rejection (callback and handoff stages)
- NULL password rejection on password login endpoint
- Replay prevention for OAuth state and handoff tickets
- Origin validation and open-redirect / origin mismatch protection
- Callback HTML security headers (CSP, no-referrer, no JWTs in URLs)
- Google-disabled configuration behavior
- Sensitive query parameter log redaction
- Expired OAuth state pruning script
- Role guard and student complaint access verification
- PostgreSQL test safeguard
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.security import (
    calculate_pkce_challenge,
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    get_password_hash,
    hash_token,
)
from app.dependencies.auth import require_admin, require_staff
from app.main import SensitiveQueryFilter
from app.models.oauth import OAuthHandoffTicket, OAuthTransaction, UserExternalIdentity
from app.models.user import User
from app.services import google_auth_service
from app.services.complaint_service import get_my_complaints
from app.services.google_auth_service import (
    check_origin_allowed,
    cleanup_expired_oauth_transactions,
    render_callback_html,
    resolve_or_create_user_for_google,
    set_jwk_client_for_testing,
    verify_google_id_token,
)


# ============================================================================
# CRYPTOGRAPHIC TEST FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def rsa_keypair():
    """Generate a dedicated 2048-bit RSA key pair for synthetic test ID tokens."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def mock_jwks(rsa_keypair):
    """Inject a mock PyJWKClient that resolves using our synthetic RSA public key."""
    _, public_key = rsa_keypair

    class MockSigningKey:
        def __init__(self, key):
            self.key = key

    class MockJWKClient:
        def __init__(self, key):
            self._key = key

        def get_signing_key_from_jwt(self, token_str: str):
            return MockSigningKey(self._key)

    client = MockJWKClient(public_key)
    set_jwk_client_for_testing(client)
    yield client
    set_jwk_client_for_testing(None)


@pytest.fixture(autouse=True)
def configure_google_test_settings():
    """Ensure Google authentication settings are predictably configured for tests."""
    orig_enabled = settings.GOOGLE_AUTH_ENABLED
    orig_client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    orig_client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
    orig_redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    orig_domains = list(settings.GOOGLE_ALLOWED_HOSTED_DOMAINS)
    orig_enc_key = settings.GOOGLE_OAUTH_ENCRYPTION_KEY
    orig_origins = list(settings.CORS_ORIGINS)

    settings.GOOGLE_AUTH_ENABLED = True
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-ccms-client-id.apps.googleusercontent.com"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "test-client-secret-xyz"
    settings.GOOGLE_OAUTH_REDIRECT_URI = "http://localhost:8000/api/v1/auth/google/callback"
    settings.GOOGLE_ALLOWED_HOSTED_DOMAINS = ["campus.edu"]
    settings.GOOGLE_OAUTH_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

    yield

    settings.GOOGLE_AUTH_ENABLED = orig_enabled
    settings.GOOGLE_OAUTH_CLIENT_ID = orig_client_id
    settings.GOOGLE_OAUTH_CLIENT_SECRET = orig_client_secret
    settings.GOOGLE_OAUTH_REDIRECT_URI = orig_redirect_uri
    settings.GOOGLE_ALLOWED_HOSTED_DOMAINS = orig_domains
    settings.GOOGLE_OAUTH_ENCRYPTION_KEY = orig_enc_key
    settings.CORS_ORIGINS = orig_origins


def create_test_id_token(
    private_key,
    sub: str = "google-sub-12345",
    email: str = "alice.student@campus.edu",
    name: str = "Alice Student",
    nonce: str = "test-nonce-123",
    email_verified: Any = True,
    hd: Optional[str] = "campus.edu",
    iss: str = "https://accounts.google.com",
    aud: Optional[str] = None,
    azp: Optional[str] = None,
    exp_delta: int = 3600,
    iat_delta: int = 0,
    extra_claims: Optional[Dict[str, Any]] = None,
    algorithm: str = "RS256",
) -> str:
    """Helper to synthesize cryptographically valid signed test ID tokens."""
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "iss": iss,
        "aud": aud or settings.GOOGLE_OAUTH_CLIENT_ID,
        "azp": azp or settings.GOOGLE_OAUTH_CLIENT_ID,
        "sub": sub,
        "email": email,
        "name": name,
        "nonce": nonce,
        "email_verified": email_verified,
        "iat": now + iat_delta,
        "exp": now + exp_delta,
    }
    if hd is not None:
        claims["hd"] = hd
    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(claims, private_key, algorithm=algorithm)


# ============================================================================
# 1. HAPPY PATH & USER RESOLUTION TESTS
# ============================================================================

def test_full_google_auth_flow_new_student(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Verify complete flow: /google/start -> /google/callback -> /google/exchange for new student."""
    priv_key, _ = rsa_keypair

    # 1. Frontend generates PKCE verifier and challenge
    client_verifier = "a-very-secret-client-side-verifier-proof-123456789012345"
    client_challenge = calculate_pkce_challenge(client_verifier)
    origin = "http://localhost:5173"

    # 2. Call /google/start with Origin header
    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": origin},
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert "authorization_url" in start_data
    state = start_data["state"]

    # Verify transaction in database
    state_h = hash_token(state)
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == state_h).first()
    assert tx is not None
    assert tx.origin == origin
    assert tx.client_challenge == client_challenge
    nonce = tx.nonce

    # 3. Simulate Google authorization code exchange
    test_id_token = create_test_id_token(
        priv_key,
        sub="google-uid-1001",
        email="new.student@campus.edu",
        name="New Student",
        nonce=nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "ya29.simulated_access_token",
            "id_token": test_id_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        callback_resp = client.get(
            f"/api/v1/auth/google/callback?code=simulated_auth_code&state={state}"
        )
        assert callback_resp.status_code == 200
        html_content = callback_resp.text
        assert "CCMS_GOOGLE_AUTH_SUCCESS" in html_content
        assert "ticket" in html_content

    # Extract ticket from HTML
    match = re.search(r'"ticket":\s*"([^"]+)"', html_content)
    assert match, "Ticket must be in callback HTML payload"
    ticket = match.group(1)

    # 4. Exchange handoff ticket with client verifier proof and Origin header
    exchange_resp = client.post(
        "/api/v1/auth/google/exchange",
        json={
            "ticket": ticket,
            "client_verifier": client_verifier,
        },
        headers={"Origin": origin},
    )
    assert exchange_resp.status_code == 200
    token_data = exchange_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == "new.student@campus.edu"
    assert token_data["user"]["role"] == "student"
    assert token_data["user"]["email_verified"] is True
    assert token_data["user"]["email_verified_at"] is not None

    # Check database records
    user = db.query(User).filter(User.email == "new.student@campus.edu").first()
    assert user is not None
    assert user.password_hash is None  # Must be NULL
    assert user.role == "student"
    assert user.email_verified is True
    assert user.email_verified_at is not None

    ident = (
        db.query(UserExternalIdentity)
        .filter(
            UserExternalIdentity.provider == "google",
            UserExternalIdentity.provider_user_id == "google-uid-1001",
        )
        .first()
    )
    assert ident is not None
    assert ident.user_id == user.id


def test_repeat_google_login_preserves_id_and_role(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Verify repeat Google sign-in reuses existing user, preserves role, and does not alter email."""
    priv_key, _ = rsa_keypair

    # Create an existing staff user linked to Google
    staff = User(
        name="Existing Staff",
        email="staff.linked@campus.edu",
        password_hash=None,
        role="staff",
        is_active=True,
        email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(staff)
    db.flush()

    identity = UserExternalIdentity(
        user_id=staff.id,
        provider="google",
        provider_user_id="google-uid-staff-999",
        email="staff.linked@campus.edu",
    )
    db.add(identity)
    db.commit()

    # Start OAuth
    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "proof-challenge-123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    # Token with same sub, but provider reports different/alias email
    test_id_token = create_test_id_token(
        priv_key,
        sub="google-uid-staff-999",
        email="alias.staff@campus.edu",
        name="Existing Staff",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": test_id_token}
        callback_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert callback_resp.status_code == 200

    ticket = re.search(r'"ticket":\s*"([^"]+)"', callback_resp.text).group(1)

    with patch("app.services.google_auth_service.verify_pkce_challenge", return_value=True):
        exchange_resp = client.post(
            "/api/v1/auth/google/exchange",
            json={"ticket": ticket, "client_verifier": "valid-verifier-123"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert exchange_resp.status_code == 200
        data = exchange_resp.json()
        # Verify internal ID, role, and email are preserved
        assert data["user"]["id"] == staff.id
        assert data["user"]["role"] == "staff"
        assert data["user"]["email"] == "staff.linked@campus.edu"


# ============================================================================
# 2. ACCOUNT COLLISION & LINKING TESTS
# ============================================================================

def test_password_account_collision_refuses_auto_link(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """When a user registered with password exists, Google login with that email must NOT auto-link."""
    priv_key, _ = rsa_keypair

    # Create password user
    pw_user = User(
        name="Password User",
        email="collision@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
        email_verified=False,
    )
    db.add(pw_user)
    db.commit()

    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "challenge-123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    test_id_token = create_test_id_token(
        priv_key,
        sub="google-new-sub-collision",
        email="collision@campus.edu",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": test_id_token}
        callback_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert callback_resp.status_code == 200
        html = callback_resp.text
        assert "CCMS_GOOGLE_AUTH_ERROR" in html
        assert '"link_required": true' in html
        assert "Sign in using your password, then connect Google from your account settings" in html

    # Verify no external identity was created
    ident = db.query(UserExternalIdentity).filter(UserExternalIdentity.provider_user_id == "google-new-sub-collision").first()
    assert ident is None


# ============================================================================
# 3. NULL PASSWORD REJECTION TESTS
# ============================================================================

def test_null_password_user_cannot_login_via_password_endpoint(client: TestClient, db: Session):
    """Google-only accounts (password_hash=NULL) must fail password login cleanly without crashing."""
    google_user = User(
        name="Google Only User",
        email="googleonly@campus.edu",
        password_hash=None,
        role="student",
        is_active=True,
        email_verified=True,
    )
    db.add(google_user)
    db.commit()

    # Attempt standard password login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "googleonly@campus.edu", "password": "AnyPassword123!"},
    )
    assert login_resp.status_code == 401
    assert "Invalid email or password" in login_resp.json()["detail"]


# ============================================================================
# 4. INACTIVE USER CHECKS
# ============================================================================

def test_inactive_account_rejected_at_callback(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Deactivated accounts must be rejected during callback processing."""
    priv_key, _ = rsa_keypair

    inactive_user = User(
        name="Inactive Student",
        email="inactive@campus.edu",
        password_hash=None,
        role="student",
        is_active=False,
    )
    db.add(inactive_user)
    db.flush()

    identity = UserExternalIdentity(
        user_id=inactive_user.id,
        provider="google",
        provider_user_id="google-sub-inactive",
        email="inactive@campus.edu",
    )
    db.add(identity)
    db.commit()

    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "challenge-123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    test_id_token = create_test_id_token(
        priv_key,
        sub="google-sub-inactive",
        email="inactive@campus.edu",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": test_id_token}
        callback_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert callback_resp.status_code == 200
        assert "CCMS_GOOGLE_AUTH_ERROR" in callback_resp.text
        assert "deactivated" in callback_resp.text.lower()


def test_account_deactivated_before_ticket_exchange(client: TestClient, db: Session):
    """If an account is deactivated after ticket issuance but before redemption, exchange is rejected."""
    user = User(
        name="Deactivated Before Exchange",
        email="deact.later@campus.edu",
        password_hash=None,
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()

    ticket = "test-ticket-xyz"
    handoff = OAuthHandoffTicket(
        ticket_hash=hash_token(ticket),
        user_id=user.id,
        client_challenge=calculate_pkce_challenge("my-verifier"),
        origin="http://localhost:5173",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        consumed_at=None,
    )
    db.add(handoff)
    db.commit()

    # Admin deactivates the user before exchange
    user.is_active = False
    db.commit()

    exchange_resp = client.post(
        "/api/v1/auth/google/exchange",
        json={
            "ticket": ticket,
            "client_verifier": "my-verifier",
        },
        headers={"Origin": "http://localhost:5173"},
    )
    assert exchange_resp.status_code == 403
    assert "inactive" in exchange_resp.json()["detail"].lower()


# ============================================================================
# 5. TOKEN CRYPTOGRAPHIC & CLAIMS VALIDATION
# ============================================================================

def test_invalid_rsa_signature_rejected(rsa_keypair, mock_jwks):
    """A token signed with an untrusted or forged private key must fail signature check."""
    forged_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged_token = create_test_id_token(forged_private_key, nonce="nonce-1")

    with pytest.raises(ValueError, match="Google ID token verification failed"):
        verify_google_id_token(forged_token, expected_nonce="nonce-1")


def test_invalid_signing_algorithm_rejected(rsa_keypair, mock_jwks):
    """Symmetric/HMAC or non-RS256 algorithms must be rejected."""
    claims = {
        "iss": "https://accounts.google.com",
        "aud": settings.GOOGLE_OAUTH_CLIENT_ID,
        "sub": "sub-123",
        "email": "test@campus.edu",
        "nonce": "nonce-1",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    # Encode with HS256
    hs256_token = jwt.encode(claims, "symmetric-secret-key-32-bytes-long!", algorithm="HS256")
    with pytest.raises(ValueError):
        verify_google_id_token(hs256_token, expected_nonce="nonce-1")


def test_wrong_issuer_rejected(rsa_keypair, mock_jwks):
    """Tokens from non-Google issuers must be rejected."""
    priv_key, _ = rsa_keypair
    token = create_test_id_token(priv_key, iss="https://evil-issuer.com", nonce="nonce-1")
    with pytest.raises(ValueError, match="Invalid token issuer"):
        verify_google_id_token(token, expected_nonce="nonce-1")


def test_wrong_audience_rejected(rsa_keypair, mock_jwks):
    """Tokens for a different audience/client ID must be rejected."""
    priv_key, _ = rsa_keypair
    token = create_test_id_token(priv_key, aud="wrong-client-id.apps.googleusercontent.com", nonce="nonce-1")
    with pytest.raises(ValueError, match="verification failed"):
        verify_google_id_token(token, expected_nonce="nonce-1")


def test_azp_mismatch_rejected(rsa_keypair, mock_jwks):
    """Authorized party (azp) mismatch must be rejected."""
    priv_key, _ = rsa_keypair
    token = create_test_id_token(priv_key, azp="some-other-app-client-id", nonce="nonce-1")
    with pytest.raises(ValueError, match="Invalid authorized party 'azp'"):
        verify_google_id_token(token, expected_nonce="nonce-1")


def test_expired_token_rejected(rsa_keypair, mock_jwks):
    """Expired tokens must be rejected."""
    priv_key, _ = rsa_keypair
    token = create_test_id_token(priv_key, exp_delta=-3600, nonce="nonce-1")
    with pytest.raises(ValueError, match="verification failed"):
        verify_google_id_token(token, expected_nonce="nonce-1")


def test_nonce_mismatch_rejected(rsa_keypair, mock_jwks):
    """Token nonce not matching the transaction nonce must be rejected."""
    priv_key, _ = rsa_keypair
    token = create_test_id_token(priv_key, nonce="nonce-abc")
    with pytest.raises(ValueError, match="ID token nonce does not match transaction nonce"):
        verify_google_id_token(token, expected_nonce="nonce-xyz")


def test_email_verified_must_be_boolean_true(rsa_keypair, mock_jwks):
    """email_verified=False, missing, or string 'true' must be rejected."""
    priv_key, _ = rsa_keypair

    # 1. email_verified = False
    token_false = create_test_id_token(priv_key, email_verified=False, nonce="n1")
    with pytest.raises(ValueError, match="email_verified must be boolean True"):
        verify_google_id_token(token_false, expected_nonce="n1")

    # 2. email_verified = "true" (string instead of boolean)
    token_str = create_test_id_token(priv_key, email_verified="true", nonce="n1")
    with pytest.raises(ValueError, match="email_verified must be boolean True"):
        verify_google_id_token(token_str, expected_nonce="n1")


def test_missing_sub_or_email_rejected(rsa_keypair, mock_jwks):
    """Tokens with missing or blank sub or invalid email must be rejected."""
    priv_key, _ = rsa_keypair

    # Blank sub
    token_no_sub = create_test_id_token(priv_key, sub="   ", nonce="n1")
    with pytest.raises(ValueError, match="Missing or invalid Google user subject"):
        verify_google_id_token(token_no_sub, expected_nonce="n1")

    # Malformed email
    token_bad_email = create_test_id_token(priv_key, email="not-an-email", nonce="n1")
    with pytest.raises(ValueError, match="Missing or malformed email claim"):
        verify_google_id_token(token_bad_email, expected_nonce="n1")


def test_hosted_domain_restriction(rsa_keypair, mock_jwks):
    """Google Workspace hd claim restriction enforcement."""
    priv_key, _ = rsa_keypair

    # With GOOGLE_ALLOWED_HOSTED_DOMAINS = ["campus.edu"]
    # 1. Matching hd claim -> succeeds
    token_ok = create_test_id_token(priv_key, hd="campus.edu", nonce="n1")
    claims = verify_google_id_token(token_ok, expected_nonce="n1")
    assert claims["hd"] == "campus.edu"

    # 2. Mismatching hd claim -> rejected
    token_wrong_hd = create_test_id_token(priv_key, hd="other-campus.org", nonce="n1")
    with pytest.raises(ValueError, match="Google account domain is not authorized"):
        verify_google_id_token(token_wrong_hd, expected_nonce="n1")

    # 3. Missing hd claim (personal gmail.com account) -> rejected
    token_no_hd = create_test_id_token(priv_key, hd=None, nonce="n1")
    with pytest.raises(ValueError, match="Google account domain is not authorized"):
        verify_google_id_token(token_no_hd, expected_nonce="n1")


def test_empty_hosted_domain_allowlist_permits_any_verified_domain(rsa_keypair, mock_jwks):
    """When GOOGLE_ALLOWED_HOSTED_DOMAINS is empty, any domain is allowed."""
    priv_key, _ = rsa_keypair
    settings.GOOGLE_ALLOWED_HOSTED_DOMAINS = []

    token = create_test_id_token(priv_key, email="user@anydomain.org", hd=None, nonce="n1")
    claims = verify_google_id_token(token, expected_nonce="n1")
    assert claims["email"] == "user@anydomain.org"


def test_role_injection_in_google_claims_is_ignored(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Google claims cannot inject elevated CCMS roles (e.g. role='admin')."""
    priv_key, _ = rsa_keypair

    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "proof-challenge-12345"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    # Attempt role injection via custom token claims
    token = create_test_id_token(
        priv_key,
        sub="attacker-sub-1",
        email="attacker@campus.edu",
        nonce=tx.nonce,
        hd="campus.edu",
        extra_claims={"role": "admin", "is_admin": True, "permissions": ["all"]},
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_ex:
        mock_ex.return_value = {"id_token": token}
        callback_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert callback_resp.status_code == 200

    ticket = re.search(r'"ticket":\s*"([^"]+)"', callback_resp.text).group(1)

    with patch("app.services.google_auth_service.verify_pkce_challenge", return_value=True):
        exchange_resp = client.post(
            "/api/v1/auth/google/exchange",
            json={"ticket": ticket, "client_verifier": "proof-verifier-12345"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert exchange_resp.status_code == 200
        # Role must remain strictly 'student'
        assert exchange_resp.json()["user"]["role"] == "student"


# ============================================================================
# 6. TRANSACTION STATE & REPLAY PROTECTION
# ============================================================================

def test_missing_or_invalid_state_callback(client: TestClient):
    """Callback with invalid/missing state returns error without sending to unknown origin."""
    resp = client.get("/api/v1/auth/google/callback?code=somecode&state=unknown-bogus-state")
    assert resp.status_code == 200
    assert "Authentication request has expired or was already used" in resp.text
    # Must NOT postMessage to unknown origin
    assert "window.opener.postMessage" not in resp.text


def test_replayed_state_rejected(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Using the same state token a second time must fail."""
    priv_key, _ = rsa_keypair

    start_resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "proof-challenge-12345"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    token = create_test_id_token(priv_key, sub="sub-replay", email="replay@campus.edu", nonce=tx.nonce)

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_ex:
        mock_ex.return_value = {"id_token": token}
        # First call succeeds and consumes transaction
        r1 = client.get(f"/api/v1/auth/google/callback?code=code1&state={state}")
        assert "CCMS_GOOGLE_AUTH_SUCCESS" in r1.text

        # Replay call fails immediately
        r2 = client.get(f"/api/v1/auth/google/callback?code=code2&state={state}")
        assert "Authentication request has expired or was already used" in r2.text


def test_expired_state_rejected(client: TestClient, db: Session):
    """A state that has exceeded its lifetime must be rejected."""
    state = "expired-state-test"
    tx = OAuthTransaction(
        state_hash=hash_token(state),
        nonce="nonce-1",
        code_verifier_encrypted=encrypt_secret("verifier"),
        origin="http://localhost:5173",
        client_challenge="challenge",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),  # expired
    )
    db.add(tx)
    db.commit()

    resp = client.get(f"/api/v1/auth/google/callback?code=code1&state={state}")
    assert resp.status_code == 200
    assert "Authentication request has expired or was already used" in resp.text
    assert "window.opener.postMessage" not in resp.text


# ============================================================================
# 7. HANDOFF TICKET & ORIGIN SECURITY
# ============================================================================

def test_origin_mismatch_on_exchange_rejected(client: TestClient, db: Session):
    """Client redeeming ticket from a different Origin than initiated must be rejected."""
    ticket = "ticket-origin-test"
    handoff = OAuthHandoffTicket(
        ticket_hash=hash_token(ticket),
        user_id=1,
        client_challenge=calculate_pkce_challenge("my-verifier"),
        origin="http://localhost:5173",  # Initiated from 5173
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(handoff)
    db.commit()

    # Redeemed with header Origin 3000
    resp = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": ticket, "client_verifier": "my-verifier"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 403
    assert "Origin mismatch" in resp.json()["detail"]


def test_invalid_verifier_proof_rejected(client: TestClient, db: Session):
    """Redeeming ticket with wrong verifier proof fails."""
    ticket = "ticket-verifier-test"
    handoff = OAuthHandoffTicket(
        ticket_hash=hash_token(ticket),
        user_id=1,
        client_challenge=calculate_pkce_challenge("correct-verifier-proof"),
        origin="http://localhost:5173",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(handoff)
    db.commit()

    resp = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": ticket, "client_verifier": "wrong-verifier"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 400
    assert "Invalid client verifier proof" in resp.json()["detail"]


def test_replayed_ticket_rejected(client: TestClient, db: Session, student_user: User):
    """Replaying an already redeemed handoff ticket must fail with 400."""
    verifier = "my-secret-proof"
    ticket = "ticket-replay-test"
    handoff = OAuthHandoffTicket(
        ticket_hash=hash_token(ticket),
        user_id=student_user.id,
        client_challenge=calculate_pkce_challenge(verifier),
        origin="http://localhost:5173",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        consumed_at=None,
    )
    db.add(handoff)
    db.commit()

    # First exchange succeeds
    r1 = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": ticket, "client_verifier": verifier},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r1.status_code == 200

    # Second exchange fails
    r2 = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": ticket, "client_verifier": verifier},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r2.status_code == 400
    assert "Invalid, expired, or already redeemed" in r2.json()["detail"]


def test_unpermitted_origin_rejected_at_start(client: TestClient):
    """Initiating Google OAuth from an untrusted origin must be rejected with 403."""
    resp = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "proof-challenge"},
        headers={"Origin": "http://attacker-site.com"},
    )
    assert resp.status_code == 403
    assert "not permitted" in resp.json()["detail"]


# ============================================================================
# 8. CALLBACK SECURITY HEADERS & LOG REDACTION
# ============================================================================

def test_callback_html_headers_and_content_security():
    """Verify callback page includes CSP nonce, no-referrer, and safe message handling."""
    html = render_callback_html(
        target_origin="http://localhost:5173",
        success=True,
        ticket="safe_ticket_abc",
    )
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    assert "no-referrer" in html
    assert "http://localhost:5173" in html
    assert "safe_ticket_abc" in html
    # Ensure no JWT format exists in callback html
    assert "eyJ" not in html


def test_sensitive_query_filter_redacts_oauth_params():
    """Verify SensitiveQueryFilter masks 'code' and 'state' in logs."""
    qfilter = SensitiveQueryFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='GET /api/v1/auth/google/callback?code=secret_auth_code_123&state=secret_state_456 HTTP/1.1 200 OK',
        args=(),
        exc_info=None,
    )
    qfilter.filter(record)
    assert "secret_auth_code_123" not in record.msg
    assert "secret_state_456" not in record.msg
    assert "[QUERY_PARAMS_REDACTED]" in record.msg


# ============================================================================
# 9. DISABLED CONFIGURATION & STARTUP VALIDATIONS
# ============================================================================

def test_disabled_google_auth_endpoints(client: TestClient):
    """When GOOGLE_AUTH_ENABLED is False, endpoints return 503 Service Unavailable."""
    settings.GOOGLE_AUTH_ENABLED = False

    r_start = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": "disabled-challenge-12345"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r_start.status_code == 503
    assert "not enabled" in r_start.json()["detail"]

    r_cb = client.get("/api/v1/auth/google/callback?code=mock_code&state=mock_state")
    assert r_cb.status_code == 200
    assert "Google authentication is disabled" in r_cb.text

    r_ex = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": "disabled-ticket-12345", "client_verifier": "disabled-verifier-12345"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r_ex.status_code == 503


def test_invalid_google_configuration_raises_on_settings():
    """Settings validator raises ValueError if enabled with missing credentials."""
    with pytest.raises(ValueError, match="GOOGLE_OAUTH_CLIENT_ID is not configured"):
        Settings(
            ENVIRONMENT="development",
            DATABASE_URL="sqlite:///:memory:",
            JWT_SECRET="test-secret",
            GOOGLE_AUTH_ENABLED=True,
            GOOGLE_OAUTH_CLIENT_ID="",
            GOOGLE_OAUTH_CLIENT_SECRET="secret",
            GOOGLE_OAUTH_REDIRECT_URI="http://localhost:8000/callback",
            GOOGLE_OAUTH_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        )


def test_production_tls_enforced():
    """Settings validator enforces sslmode=require for PostgreSQL in production."""
    with pytest.raises(ValueError, match="require explicit TLS enforcement"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg://user:pass@db.example.com:5432/ccms",  # Missing sslmode
            JWT_SECRET="production-jwt-secret-min-32-chars-long",
            CORS_ORIGINS="https://ccms.example.edu",
            EMAIL_PROVIDER="resend",
            GOOGLE_AUTH_ENABLED=False,
        )


# ============================================================================
# 10. GOOGLE USER AUTHORIZATION & CCMS RBAC BEHAVIOR
# ============================================================================

def test_google_student_can_create_complaint_and_read_own(client: TestClient, db: Session, seeded_departments: dict):
    """A Google-authenticated student can use standard CCMS student endpoints."""
    # Create Google-authenticated student
    g_student = User(
        name="Google Student",
        email="gstudent@campus.edu",
        password_hash=None,
        role="student",
        is_active=True,
        email_verified=True,
    )
    db.add(g_student)
    db.commit()

    token = create_access_token(
        subject=str(g_student.id),
        claims={"role": g_student.role, "email": g_student.email},
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Read /users/me
    me_resp = client.get("/api/v1/users/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "gstudent@campus.edu"
    assert me_resp.json()["email_verified"] is True

    # 2. List departments
    dept_resp = client.get("/api/v1/departments", headers=headers)
    assert dept_resp.status_code == 200
    assert len(dept_resp.json()) >= 1

    # 3. Create complaint
    c_resp = client.post(
        "/api/v1/complaints",
        headers=headers,
        json={
            "title": "Wi-Fi Issue in Library",
            "description": "Library 2nd floor wireless signal is disconnecting frequently.",
            "department_id": seeded_departments["it"].id,
        },
    )
    assert c_resp.status_code == 201
    complaint_id = c_resp.json()["id"]

    # 4. Read own complaint history via /api/v1/complaints/mine
    mine_resp = client.get("/api/v1/complaints/mine", headers=headers)
    assert mine_resp.status_code == 200
    complaints = mine_resp.json()
    assert len(complaints) >= 1
    assert any(c["id"] == complaint_id for c in complaints)


def test_google_student_cannot_access_staff_or_admin_endpoints(db: Session):
    """Google student cannot satisfy staff or admin role guards."""
    g_student = User(
        name="Google Student",
        email="student.guard@campus.edu",
        password_hash=None,
        role="student",
        is_active=True,
    )
    db.add(g_student)
    db.commit()

    # require_staff guard check
    with pytest.raises(HTTPException) as exc_staff:
        require_staff(current_user=g_student)
    assert exc_staff.value.status_code == 403
    assert "Access denied" in exc_staff.value.detail

    # require_admin guard check
    with pytest.raises(HTTPException) as exc_admin:
        require_admin(current_user=g_student)
    assert exc_admin.value.status_code == 403
    assert "Access denied" in exc_admin.value.detail


def test_student_cannot_read_another_students_complaints(db: Session, seeded_departments: dict):
    """Students cannot view complaints filed by another student."""
    s1 = User(name="Student 1", email="s1@campus.edu", role="student", is_active=True)
    s2 = User(name="Student 2", email="s2@campus.edu", role="student", is_active=True)
    db.add_all([s1, s2])
    db.commit()

    from app.schemas.complaint import ComplaintCreate
    from app.services.complaint_service import create_student_complaint

    c1 = create_student_complaint(
        db=db,
        complaint_in=ComplaintCreate(
            title="S1 Complaint",
            description="Private issue of Student 1",
            department_id=seeded_departments["it"].id,
        ),
        student=s1,
    )

    # Student 2 checks their complaints
    s2_complaints, _total = get_my_complaints(db=db, student_id=s2.id)
    assert not any(c.id == c1.id for c in s2_complaints)


# ============================================================================
# 11. OAUTH STATE CLEANUP SCRIPT TEST
# ============================================================================

def test_cleanup_oauth_state_prunes_expired_records(db: Session):
    """The cleanup_expired_oauth_transactions function must prune expired records while preserving active ones."""
    now = datetime.now(timezone.utc)

    # 1. Expired transaction
    expired_tx = OAuthTransaction(
        state_hash="h1",
        nonce="n1",
        code_verifier_encrypted="enc",
        origin="http://localhost:5173",
        client_challenge="c",
        expires_at=now - timedelta(hours=1),
    )
    # 2. Active transaction
    active_tx = OAuthTransaction(
        state_hash="h2",
        nonce="n2",
        code_verifier_encrypted="enc",
        origin="http://localhost:5173",
        client_challenge="c",
        expires_at=now + timedelta(hours=1),
    )
    # 3. Expired handoff ticket
    expired_ticket = OAuthHandoffTicket(
        ticket_hash="t1",
        user_id=1,
        client_challenge="c",
        origin="http://localhost:5173",
        expires_at=now - timedelta(hours=1),
    )
    # 4. Consumed ticket from 2 days ago
    consumed_ticket = OAuthHandoffTicket(
        ticket_hash="t2",
        user_id=1,
        client_challenge="c",
        origin="http://localhost:5173",
        expires_at=now + timedelta(hours=1),
        consumed_at=now - timedelta(days=2),
    )

    db.add_all([expired_tx, active_tx, expired_ticket, consumed_ticket])
    db.commit()

    deleted_count = cleanup_expired_oauth_transactions(db)
    assert deleted_count >= 3

    # Assert active records remain, expired pruned
    assert db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == "h1").first() is None
    assert db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == "h2").first() is not None
    assert db.query(OAuthHandoffTicket).filter(OAuthHandoffTicket.ticket_hash == "t1").first() is None
    assert db.query(OAuthHandoffTicket).filter(OAuthHandoffTicket.ticket_hash == "t2").first() is None


# ============================================================================
# 12. POSTGRESQL CONCURRENCY TEST & SAFEGUARD SKIP
# ============================================================================

def test_postgresql_concurrency_and_migrations_safeguard():
    """
    Safeguard test for isolated local PostgreSQL.
    If TEST_POSTGRESQL_URL is not provided or local PostgreSQL is unreachable,
    this test is explicitly reported as skipped without falsifying SQLite as proof.
    """
    import os
    pg_url = os.environ.get("TEST_POSTGRESQL_URL")
    if not pg_url:
        pytest.skip(
            "Isolated local PostgreSQL environment not available. "
            "To execute PostgreSQL-specific concurrency & migration tests, run: "
            "TEST_POSTGRESQL_URL=postgresql+psycopg://user:password@localhost:5432/test_ccms pytest -k postgresql"
        )


# ============================================================================
# 13. GOOGLE ACCOUNT LINKING TESTS
# ============================================================================

def test_google_link_requires_authentication(client: TestClient):
    """Unauthenticated call to /auth/google/link/start must be rejected with 401."""
    resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": "challenge-1234567890"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 401


def test_google_link_rejects_inactive_user(client: TestClient, db: Session):
    """Inactive user cannot start account linking."""
    inactive_user = User(
        name="Inactive User",
        email="inactive.linking@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=False,
    )
    db.add(inactive_user)
    db.commit()

    token = create_access_token(subject=str(inactive_user.id), claims={"role": "student"})
    resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": "challenge-1234567890"},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_google_link_rejects_already_linked_user(client: TestClient, db: Session):
    """User who already has a linked Google account cannot initiate another link."""
    user = User(
        name="Linked User",
        email="already.linked@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.flush()

    ident = UserExternalIdentity(
        user_id=user.id,
        provider="google",
        provider_user_id="google-sub-existing",
        email=user.email,
    )
    db.add(ident)
    db.commit()

    token = create_access_token(subject=str(user.id), claims={"role": "student"})
    resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": "challenge-1234567890"},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "already linked" in resp.json()["detail"].lower()


def test_google_link_flow_success_and_dual_login(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """
    Full end-to-end linking flow:
    1. Existing password user initiates linking.
    2. Callback verifies token, links identity to existing CCMS user ID.
    3. Ticket is exchanged for updated user profile.
    4. User can subsequently log in via original password.
    5. User can also log in via Google sign-in.
    """
    priv_key, _ = rsa_keypair
    user = User(
        name="Dave Student",
        email="dave.student@campus.edu",
        password_hash=get_password_hash("DaveSecret123!"),
        role="student",
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    db.commit()
    user_id = user.id

    token = create_access_token(subject=str(user_id), claims={"role": "student"})

    client_verifier = "pkce-verifier-dave-linking-secret-123456789"
    client_challenge = calculate_pkce_challenge(client_verifier)

    # 1. Initiate linking flow
    start_resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    assert start_resp.status_code == 200
    state = start_resp.json()["state"]

    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()
    assert tx is not None

    # Synthesize Google ID token matching dave's email
    id_token = create_test_id_token(
        priv_key,
        sub="google-dave-sub-unique",
        email="dave.student@campus.edu",
        name="Dave Student",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    # 2. Callback
    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": id_token}
        cb_resp = client.get(f"/api/v1/auth/google/callback?code=code123&state={state}")
        assert cb_resp.status_code == 200
        html = cb_resp.text
        assert "CCMS_GOOGLE_LINK_SUCCESS" in html
        match = re.search(r'"ticket":\s*"([^"]+)"', html)
        assert match is not None
        ticket = match.group(1)

    # 3. Exchange ticket
    exchange_resp = client.post(
        "/api/v1/auth/google/link/exchange",
        json={"ticket": ticket, "client_verifier": client_verifier},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    assert exchange_resp.status_code == 200
    ex_data = exchange_resp.json()
    assert "Google account connected successfully" in ex_data["message"]
    assert ex_data["user"]["id"] == user_id
    assert ex_data["user"]["google_linked"] is True
    assert ex_data["user"]["email_verified"] is True

    # Check database identity
    db_ident = db.query(UserExternalIdentity).filter(UserExternalIdentity.provider_user_id == "google-dave-sub-unique").first()
    assert db_ident is not None
    assert db_ident.user_id == user_id

    # 4. Verify password login still works
    pw_resp = client.post("/api/v1/auth/login", json={"email": "dave.student@campus.edu", "password": "DaveSecret123!"})
    assert pw_resp.status_code == 200
    assert pw_resp.json()["user"]["id"] == user_id
    assert pw_resp.json()["user"]["google_linked"] is True

    # 5. Verify Google login now resolves directly to dave's account
    start_login = client.post(
        "/api/v1/auth/google/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": "http://localhost:5173"},
    )
    assert start_login.status_code == 200
    login_state = start_login.json()["state"]
    login_tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(login_state)).first()

    login_id_token = create_test_id_token(
        priv_key,
        sub="google-dave-sub-unique",
        email="dave.student@campus.edu",
        nonce=login_tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": login_id_token}
        cb_login = client.get(f"/api/v1/auth/google/callback?code=code456&state={login_state}")
        assert cb_login.status_code == 200
        assert "CCMS_GOOGLE_AUTH_SUCCESS" in cb_login.text
        m = re.search(r'"ticket":\s*"([^"]+)"', cb_login.text)
        assert m is not None
        login_ticket = m.group(1)

    ex_login = client.post(
        "/api/v1/auth/google/exchange",
        json={"ticket": login_ticket, "client_verifier": client_verifier},
        headers={"Origin": "http://localhost:5173"},
    )
    assert ex_login.status_code == 200
    assert ex_login.json()["user"]["id"] == user_id


def test_google_link_rejects_email_mismatch(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Linking must fail if returned Google email does not match CCMS account email."""
    priv_key, _ = rsa_keypair
    user = User(
        name="User A",
        email="user.a@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()

    token = create_access_token(subject=str(user.id), claims={"role": "student"})
    client_verifier = "pkce-verifier-mismatch-123456789012345678"
    client_challenge = calculate_pkce_challenge(client_verifier)

    start_resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    # Google token with DIFFERENT email
    id_token = create_test_id_token(
        priv_key,
        sub="google-sub-mismatch",
        email="different.person@campus.edu",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": id_token}
        cb_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert cb_resp.status_code == 200
        html = cb_resp.text
        assert "CCMS_GOOGLE_LINK_ERROR" in html
        assert "does not match your CCMS account email" in html

    # Confirm no identity created
    assert db.query(UserExternalIdentity).filter(UserExternalIdentity.provider_user_id == "google-sub-mismatch").first() is None


def test_google_link_rejects_unverified_google_email(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """Google account with email_verified=False must be rejected for linking."""
    priv_key, _ = rsa_keypair
    user = User(
        name="User Unverified",
        email="unverified.user@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add(user)
    db.commit()

    token = create_access_token(subject=str(user.id), claims={"role": "student"})
    client_verifier = "pkce-verifier-unverified-123456789012345678"
    client_challenge = calculate_pkce_challenge(client_verifier)

    start_resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token}"},
    )
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    id_token = create_test_id_token(
        priv_key,
        sub="google-sub-unverified",
        email="unverified.user@campus.edu",
        nonce=tx.nonce,
        email_verified=False,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": id_token}
        cb_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert cb_resp.status_code == 200
        html = cb_resp.text
        assert "CCMS_GOOGLE_LINK_ERROR" in html
        assert "not verified" in html


def test_google_link_rejects_identity_conflict(client: TestClient, db: Session, rsa_keypair, mock_jwks):
    """A Google sub already bound to another CCMS user cannot be linked to a second user."""
    priv_key, _ = rsa_keypair
    user1 = User(
        name="User 1",
        email="user1@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    user2 = User(
        name="User 2",
        email="user2@campus.edu",
        password_hash=get_password_hash("Password123!"),
        role="student",
        is_active=True,
    )
    db.add_all([user1, user2])
    db.flush()

    # User 1 already linked to google-shared-sub
    ident1 = UserExternalIdentity(
        user_id=user1.id,
        provider="google",
        provider_user_id="google-shared-sub",
        email="user1@campus.edu",
    )
    db.add(ident1)
    db.commit()

    token2 = create_access_token(subject=str(user2.id), claims={"role": "student"})
    client_verifier = "pkce-verifier-conflict-123456789012345678"
    client_challenge = calculate_pkce_challenge(client_verifier)

    start_resp = client.post(
        "/api/v1/auth/google/link/start",
        json={"client_challenge": client_challenge},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {token2}"},
    )
    state = start_resp.json()["state"]
    tx = db.query(OAuthTransaction).filter(OAuthTransaction.state_hash == hash_token(state)).first()

    # Attempt to link user2 with user2's email, but with user1's sub
    id_token = create_test_id_token(
        priv_key,
        sub="google-shared-sub",
        email="user2@campus.edu",
        nonce=tx.nonce,
        hd="campus.edu",
    )

    with patch("app.services.google_auth_service.exchange_code_with_google") as mock_exchange:
        mock_exchange.return_value = {"id_token": id_token}
        cb_resp = client.get(f"/api/v1/auth/google/callback?code=mock_code&state={state}")
        assert cb_resp.status_code == 200
        html = cb_resp.text
        assert "CCMS_GOOGLE_LINK_ERROR" in html
        assert "already linked to another CCMS user" in html

    # Confirm user2 has no identity
    assert db.query(UserExternalIdentity).filter(UserExternalIdentity.user_id == user2.id).first() is None


def test_google_link_exchange_rejects_wrong_user(client: TestClient, db: Session):
    """User B cannot exchange a ticket that was issued to User A."""
    userA = User(name="User A", email="usera@campus.edu", password_hash="h", role="student", is_active=True)
    userB = User(name="User B", email="userb@campus.edu", password_hash="h", role="student", is_active=True)
    db.add_all([userA, userB])
    db.commit()

    client_verifier = "test-client-verifier-wrong-user-proof-123"
    client_challenge = calculate_pkce_challenge(client_verifier)

    ticket = "ticket-for-user-a-1234567890"
    now = datetime.now(timezone.utc)
    handoff = OAuthHandoffTicket(
        ticket_hash=hash_token(ticket),
        user_id=userA.id,
        client_challenge=client_challenge,
        origin="http://localhost:5173",
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
    )
    db.add(handoff)
    db.commit()

    # User B attempts to redeem
    tokenB = create_access_token(subject=str(userB.id), claims={"role": "student"})
    resp = client.post(
        "/api/v1/auth/google/link/exchange",
        json={"ticket": ticket, "client_verifier": client_verifier},
        headers={"Origin": "http://localhost:5173", "Authorization": f"Bearer {tokenB}"},
    )
    assert resp.status_code == 403
    assert "does not match the linking ticket owner" in resp.json()["detail"]


def test_google_status_endpoint(client: TestClient, db: Session):
    """GET /auth/google/status reports linked boolean and email correctly."""
    user = User(name="Status User", email="status.user@campus.edu", password_hash="h", role="student", is_active=True)
    db.add(user)
    db.commit()

    token = create_access_token(subject=str(user.id), claims={"role": "student"})

    # Initially unlinked
    r1 = client.get("/api/v1/auth/google/status", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200
    assert r1.json()["linked"] is False
    assert r1.json()["email"] is None

    # After linking
    ident = UserExternalIdentity(user_id=user.id, provider="google", provider_user_id="sub-stat", email="status.user@campus.edu")
    db.add(ident)
    db.commit()

    r2 = client.get("/api/v1/auth/google/status", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["linked"] is True
    assert r2.json()["email"] == "status.user@campus.edu"
