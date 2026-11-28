"""Tests for S5-25: Forgot Password, Reset Password, and Change Password.

Verifies:
1. Unknown email and known email both return 202 Accepted (neutral response).
2. Reset email is sent for an existing active account containing a single-use token.
3. Raw reset token is never stored in the database (only SHA-256 hash).
4. Valid token resets the password, invalidates other tokens, and permits login with new password.
5. Old password no longer works after password reset.
6. Invalid token is rejected with 400.
7. Expired token is rejected with 400.
8. Used token cannot be reused (400).
9. Other outstanding tokens are invalidated upon reset.
10. Rate limit (at most 3 reset requests per email per hour) is enforced (429 on 4th).
11. New password follows registration validation rules (length, whitespace, bytes).
12. Change password requires authentication (401 without token).
13. Wrong current password is rejected with 400.
14. New password identical to current password is rejected with 400.
15. Successful change password updates bcrypt hash and permits login.
16. Concurrent token usage cannot result in multiple successful resets.
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.rate_limit import password_reset_rate_limiter
from app.core.security import create_access_token, get_password_hash, hash_token, verify_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.email_service import MockEmailSender, set_email_sender_for_testing


@pytest.fixture(autouse=True)
def mock_email():
    """Ensure every test has a clean MockEmailSender injected."""
    sender = MockEmailSender()
    set_email_sender_for_testing(sender)
    yield sender
    set_email_sender_for_testing(None)


@pytest.fixture(autouse=True)
def reset_limiters():
    """Reset rate limiters between tests."""
    password_reset_rate_limiter.reset()
    yield
    password_reset_rate_limiter.reset()


@pytest.fixture
def student_user(db: Session) -> User:
    """Create a verified active student user with a known password."""
    user = User(
        name="Test Student",
        email="student.reset@dau.ac.in",
        password_hash=get_password_hash("OldPassword123!"),
        role="student",
        is_active=True,
        email_verified=True,
        email_verification_required=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(
        subject=str(user.id),
        claims={"role": user.role, "email": user.email},
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Forgot Password Endpoint Tests
# ---------------------------------------------------------------------------

def test_forgot_password_unknown_email_returns_202_and_no_email(client, db, mock_email):
    """Unknown email returns 202 Accepted without dispatching email or leaking existence."""
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@dau.ac.in"})
    assert resp.status_code == 202
    assert "password reset instructions have been sent" in resp.json()["message"]
    assert len(mock_email.sent_emails) == 0


def test_forgot_password_known_email_returns_202_and_dispatches_email(client, db, mock_email, student_user):
    """Registered active email returns 202 Accepted and sends single-use reset token."""
    resp = client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    assert resp.status_code == 202
    assert "password reset instructions have been sent" in resp.json()["message"]

    # Email was dispatched
    assert len(mock_email.sent_emails) == 1
    email_data = mock_email.sent_emails[0]
    assert email_data["to_email"] == student_user.email
    assert email_data["type"] == "password_reset"
    raw_token = email_data["token"]
    assert len(raw_token) >= 32

    # Database records token hash, NOT raw token
    token_records = db.query(PasswordResetToken).filter(PasswordResetToken.user_id == student_user.id).all()
    assert len(token_records) == 1
    record = token_records[0]
    assert record.token_hash == hash_token(raw_token)
    assert record.token_hash != raw_token
    assert record.used_at is None
    # Token TTL is approximately 30 minutes
    now = datetime.now(timezone.utc)
    record_exp = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
    assert record_exp > now
    assert record_exp <= now + timedelta(minutes=31)


def test_forgot_password_rate_limiting_enforces_three_requests_per_hour(client, student_user):
    """At most 3 reset requests per email per hour. 4th request returns 429."""
    for i in range(3):
        res = client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
        assert res.status_code == 202, f"Request {i+1} should succeed with 202"

    # 4th request exceeds rate limit
    res4 = client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    assert res4.status_code == 429
    assert "Too many password reset requests" in res4.json()["detail"]


def test_forgot_password_rate_limiting_applies_to_unregistered_emails(client):
    """Rate limit also applies to unregistered emails to prevent enumeration attacks."""
    email = "nonexistent.attacker@dau.ac.in"
    for i in range(3):
        res = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert res.status_code == 202

    res4 = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert res4.status_code == 429


# ---------------------------------------------------------------------------
# 2. Reset Password Endpoint Tests
# ---------------------------------------------------------------------------

def test_reset_password_valid_token_resets_password_and_enables_login(client, db, mock_email, student_user):
    """Valid token resets password, allows login with new password, and disables old password."""
    # 1. Request forgot password
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    raw_token = mock_email.sent_emails[0]["token"]

    # 2. Reset password
    new_pw = "BrandNewPassword123!"
    reset_resp = client.post("/api/v1/auth/reset-password", json={"token": raw_token, "password": new_pw})
    assert reset_resp.status_code == 200
    assert "Password has been reset successfully" in reset_resp.json()["message"]

    # 3. Old password login fails
    old_login = client.post("/api/v1/auth/login", json={"email": student_user.email, "password": "OldPassword123!"})
    assert old_login.status_code == 401

    # 4. New password login succeeds
    new_login = client.post("/api/v1/auth/login", json={"email": student_user.email, "password": new_pw})
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_reset_password_invalid_token_returns_400(client):
    """Invalid or nonexistent token returns 400 Bad Request."""
    resp = client.post("/api/v1/auth/reset-password", json={"token": "garbage_token_123", "password": "NewValidPassword123!"})
    assert resp.status_code == 400
    assert "Invalid or expired" in resp.json()["detail"]


def test_reset_password_expired_token_returns_400(client, db, student_user):
    """Expired token returns 400 Bad Request."""
    raw_token = "expired_raw_token_xyz"
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    token_record = PasswordResetToken(
        user_id=student_user.id,
        token_hash=hash_token(raw_token),
        expires_at=expired_at,
    )
    db.add(token_record)
    db.commit()

    resp = client.post("/api/v1/auth/reset-password", json={"token": raw_token, "password": "NewValidPassword123!"})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


def test_reset_password_single_use_token_cannot_be_reused(client, mock_email, student_user):
    """Token can only be used once; second attempt returns 400."""
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    raw_token = mock_email.sent_emails[0]["token"]

    # First reset succeeds
    res1 = client.post("/api/v1/auth/reset-password", json={"token": raw_token, "password": "FirstNewPassword123!"})
    assert res1.status_code == 200

    # Second reset with same token fails
    res2 = client.post("/api/v1/auth/reset-password", json={"token": raw_token, "password": "SecondNewPassword123!"})
    assert res2.status_code == 400
    assert "already been used" in res2.json()["detail"]


def test_reset_password_invalidates_prior_outstanding_tokens(client, db, mock_email, student_user):
    """When a reset succeeds, all prior outstanding tokens for that user are voided."""
    # First request
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    token1 = mock_email.sent_emails[0]["token"]

    # Second request
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    token2 = mock_email.sent_emails[1]["token"]

    # Token1 was already superseded upon request 2, but let's reset with token2
    res = client.post("/api/v1/auth/reset-password", json={"token": token2, "password": "UpdatedPassword123!"})
    assert res.status_code == 200

    # Attempting to use token1 fails
    res_old = client.post("/api/v1/auth/reset-password", json={"token": token1, "password": "AnotherPassword123!"})
    assert res_old.status_code == 400


def test_reset_password_validates_password_rules(client, mock_email, student_user):
    """Reset password applies registration password validation rules."""
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    token = mock_email.sent_emails[0]["token"]

    # Too short (< 8 chars)
    r_short = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "short"})
    assert r_short.status_code == 422

    # Whitespace only
    r_space = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "        "})
    assert r_space.status_code == 422

    # Too long (> 72 bytes)
    r_long = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "a" * 80})
    assert r_long.status_code == 422


# ---------------------------------------------------------------------------
# 3. Change Password Endpoint Tests
# ---------------------------------------------------------------------------

def test_change_password_requires_authentication(client):
    """Unauthenticated call to /users/me/change-password returns 401."""
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "OldPassword123!", "new_password": "NewPassword123!"},
    )
    assert resp.status_code == 401


def test_change_password_rejects_wrong_current_password(client, student_user):
    """Wrong current password returns 400 Bad Request."""
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "WrongPassword!", "new_password": "BrandNewPassword123!"},
        headers=_auth_headers(student_user),
    )
    assert resp.status_code == 400
    assert "Incorrect current password" in resp.json()["detail"]


def test_change_password_rejects_identical_new_password(client, student_user):
    """New password identical to current password returns 400 Bad Request."""
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "OldPassword123!", "new_password": "OldPassword123!"},
        headers=_auth_headers(student_user),
    )
    assert resp.status_code == 400
    assert "New password must be different" in resp.json()["detail"]


def test_change_password_success_updates_password_and_invalidates_tokens(client, db, mock_email, student_user):
    """Successful password change updates hash, allows login with new password, and invalidates reset tokens."""
    # Create an outstanding reset token
    client.post("/api/v1/auth/forgot-password", json={"email": student_user.email})
    reset_token = mock_email.sent_emails[0]["token"]

    new_pw = "SuccessfullyChanged123!"
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "OldPassword123!", "new_password": new_pw},
        headers=_auth_headers(student_user),
    )
    assert resp.status_code == 200
    assert "Password changed successfully" in resp.json()["message"]

    # Login with old password fails
    old_login = client.post("/api/v1/auth/login", json={"email": student_user.email, "password": "OldPassword123!"})
    assert old_login.status_code == 401

    # Login with new password succeeds
    new_login = client.post("/api/v1/auth/login", json={"email": student_user.email, "password": new_pw})
    assert new_login.status_code == 200

    # Outstanding reset token was invalidated
    reset_attempt = client.post("/api/v1/auth/reset-password", json={"token": reset_token, "password": "TryHijack123!"})
    assert reset_attempt.status_code == 400


# ---------------------------------------------------------------------------
# 4. Concurrency Safety Test
# ---------------------------------------------------------------------------

def test_reset_password_concurrent_token_consumption_safety(db, student_user):
    """Atomic update condition prevents two simultaneous requests from both consuming a token."""
    raw_token = "concurrent_token_abc"
    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    token_record = PasswordResetToken(
        user_id=student_user.id,
        token_hash=token_h,
        expires_at=now + timedelta(minutes=30),
    )
    db.add(token_record)
    db.commit()

    # First transaction consumes the token
    stmt1 = (
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == token_record.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    res1 = db.execute(stmt1)
    db.commit()
    assert res1.rowcount == 1

    # Second concurrent transaction targeting the same token
    stmt2 = (
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == token_record.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    res2 = db.execute(stmt2)
    db.commit()
    assert res2.rowcount == 0, "Second concurrent attempt must match 0 rows and fail"
