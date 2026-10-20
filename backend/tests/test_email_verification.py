from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import update

from app.core.security import get_password_hash, hash_token
from app.models.user import User
from app.models.verification_token import EmailVerificationToken
from app.services.email_service import MockEmailSender, set_email_sender_for_testing


@pytest.fixture(autouse=True)
def mock_email():
    """Ensure every test has a clean MockEmailSender injected."""
    sender = MockEmailSender()
    set_email_sender_for_testing(sender)
    yield sender
    set_email_sender_for_testing(None)


def test_1_new_registration_creates_unverified_student_requiring_verification_no_jwt(client, db, mock_email):
    """1. New registration creates an unverified student account requiring verification and does not return a JWT."""
    payload = {
        "name": "Aarav Patel",
        "email": "aarav.patel@dau.ac.in",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    # Public safe response assertions
    assert data["name"] == "Aarav Patel"
    assert data["email"] == "aarav.patel@dau.ac.in"
    assert data["role"] == "student"
    assert data["email_verified"] is False
    assert data["email_verification_required"] is True
    assert "access_token" not in data
    assert "token_type" not in data
    assert "message" in data

    # Verify directly in database
    user = db.query(User).filter(User.email == "aarav.patel@dau.ac.in").first()
    assert user is not None
    assert user.role == "student"
    assert user.email_verified is False
    assert user.email_verification_required is True

    # Check that an email was sent via mock sender
    assert len(mock_email.sent_emails) == 1
    assert mock_email.sent_emails[0]["to_email"] == "aarav.patel@dau.ac.in"


def test_2_raw_verification_tokens_are_not_stored_in_database(client, db, mock_email):
    """2. Raw verification tokens are not stored in the database."""
    payload = {
        "name": "Sec Student",
        "email": "sec.student@dau.ac.in",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    raw_token = mock_email.sent_emails[0]["token"]
    assert len(raw_token) >= 32

    user = db.query(User).filter(User.email == "sec.student@dau.ac.in").first()
    tokens = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).all()
    assert len(tokens) == 1
    stored_token = tokens[0]

    # Stored token is a 64-char SHA-256 hash, NOT the raw token
    assert stored_token.token_hash != raw_token
    assert stored_token.token_hash == hash_token(raw_token)
    assert len(stored_token.token_hash) == 64


def test_3_valid_token_verifies_correct_user(client, db, mock_email):
    """3. A valid token verifies the correct user without issuing a JWT."""
    payload = {
        "name": "Verify Me",
        "email": "verify.me@dau.ac.in",
        "password": "StrongPassword123!",
    }
    client.post("/api/v1/auth/register", json=payload)
    raw_token = mock_email.sent_emails[0]["token"]

    verify_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert "verified successfully" in verify_data["message"].lower()
    assert verify_data["email"] == "verify.me@dau.ac.in"
    assert "access_token" not in verify_data

    # Check DB state
    user = db.query(User).filter(User.email == "verify.me@dau.ac.in").first()
    assert user.email_verified is True
    assert user.email_verified_at is not None

    token_record = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).first()
    assert token_record.used_at is not None


def test_4_expired_tokens_are_rejected(client, db, mock_email):
    """4. Expired tokens are rejected."""
    payload = {
        "name": "Expire Me",
        "email": "expire.me@dau.ac.in",
        "password": "StrongPassword123!",
    }
    client.post("/api/v1/auth/register", json=payload)
    raw_token = mock_email.sent_emails[0]["token"]

    user = db.query(User).filter(User.email == "expire.me@dau.ac.in").first()
    token_record = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).first()

    # Simulate token expiration 10 minutes in the past
    token_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    verify_res = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verify_res.status_code == 400
    assert "expired" in verify_res.json()["detail"].lower()

    # User remains unverified
    db.refresh(user)
    assert user.email_verified is False


def test_5_consumed_tokens_cannot_be_reused_deterministic_conditional_update(client, db, mock_email):
    """5. Consumed tokens cannot be reused; verify atomic conditional-update logic deterministically."""
    payload = {
        "name": "Single Use",
        "email": "single.use@dau.ac.in",
        "password": "StrongPassword123!",
    }
    client.post("/api/v1/auth/register", json=payload)
    raw_token = mock_email.sent_emails[0]["token"]

    # First attempt: succeeds
    res1 = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert res1.status_code == 200

    # Second sequential attempt: rejected
    res2 = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert res2.status_code == 400
    assert "already been used" in res2.json()["detail"].lower()

    # Deterministic conditional-consumption test at the database level:
    # UPDATE verification_tokens SET used_at = :now WHERE token_hash = :hash AND used_at IS NULL AND expires_at > :now
    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)
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

    # Exactly 0 rows affected because token is already consumed
    assert result.rowcount == 0


def test_6_token_cannot_verify_another_users_account(client, db, mock_email):
    """6. Tokens cannot verify another user's account."""
    client.post(
        "/api/v1/auth/register",
        json={"name": "Student Alpha", "email": "alpha@dau.ac.in", "password": "Password123!"},
    )
    token_alpha = mock_email.sent_emails[0]["token"]

    client.post(
        "/api/v1/auth/register",
        json={"name": "Student Beta", "email": "beta@dau.ac.in", "password": "Password123!"},
    )
    token_beta = mock_email.sent_emails[1]["token"]

    # Verify using Token Alpha
    res = client.post("/api/v1/auth/verify-email", json={"token": token_alpha})
    assert res.status_code == 200

    # Check Student Alpha is verified
    user_alpha = db.query(User).filter(User.email == "alpha@dau.ac.in").first()
    assert user_alpha.email_verified is True

    # Check Student Beta is STILL unverified
    user_beta = db.query(User).filter(User.email == "beta@dau.ac.in").first()
    assert user_beta.email_verified is False


def test_7_email_delivery_failure_does_not_mark_verified_or_falsely_report_success(client, db, mock_email):
    """7. Email delivery failure does not mark account verified or falsely report successful delivery."""
    mock_email.should_fail = True

    payload = {
        "name": "Delivery Fail",
        "email": "fail.delivery@dau.ac.in",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 502
    assert "could not be delivered" in response.json()["detail"].lower()

    # User remains unverified in database in recoverable state
    user = db.query(User).filter(User.email == "fail.delivery@dau.ac.in").first()
    assert user is not None
    assert user.email_verified is False
    assert user.email_verification_required is True

    # Token is created and unconsumed
    tokens = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).all()
    assert len(tokens) == 1
    assert tokens[0].used_at is None


def test_8_resend_creates_new_token_and_invalidates_previous_unused_token(client, db, mock_email):
    """8. Resend creates a new token and invalidates the previous unused token."""
    email = "resend.student@dau.ac.in"
    client.post(
        "/api/v1/auth/register",
        json={"name": "Resend Student", "email": email, "password": "StrongPassword123!"},
    )
    token_1 = mock_email.sent_emails[0]["token"]

    user = db.query(User).filter(User.email == email).first()
    t1_record = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).first()
    assert t1_record.used_at is None

    # Resend verification
    resend_res = client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert resend_res.status_code == 200
    assert len(mock_email.sent_emails) == 2
    token_2 = mock_email.sent_emails[1]["token"]
    assert token_1 != token_2

    # Verify in DB: t1 is now marked used/invalidated
    db.refresh(t1_record)
    assert t1_record.used_at is not None

    # Attempting to use old token 1 fails
    fail_res = client.post("/api/v1/auth/verify-email", json={"token": token_1})
    assert fail_res.status_code == 400
    assert "already been used" in fail_res.json()["detail"].lower()

    # Using fresh token 2 succeeds
    success_res = client.post("/api/v1/auth/verify-email", json={"token": token_2})
    assert success_res.status_code == 200
    db.refresh(user)
    assert user.email_verified is True


def test_9_unverified_account_requiring_verification_cannot_obtain_jwt(client, db):
    """9. Unverified accounts requiring verification cannot obtain a JWT."""
    email = "unverified.lockout@dau.ac.in"
    client.post(
        "/api/v1/auth/register",
        json={"name": "Unverified Student", "email": email, "password": "StrongPassword123!"},
    )

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword123!"})
    assert login_res.status_code == 403
    assert "not been verified" in login_res.json()["detail"].lower()
    assert "access_token" not in login_res.json()


def test_10_verified_accounts_can_log_in_normally(client, db, mock_email):
    """10. Verified accounts can log in normally."""
    email = "verified.login@dau.ac.in"
    client.post(
        "/api/v1/auth/register",
        json={"name": "Verified Student", "email": email, "password": "StrongPassword123!"},
    )
    raw_token = mock_email.sent_emails[0]["token"]
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword123!"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token

    me_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email


def test_11_legacy_accounts_retain_behavior_and_are_exempt(client, db):
    """11. Legacy accounts retain the behavior defined in Section 3 (not locked out, not falsely verified)."""
    # Create legacy account (email_verification_required=False, email_verified=False)
    legacy_user = User(
        name="Legacy Student",
        email="legacy.student@dau.ac.in",
        password_hash=get_password_hash("LegacyPass123!"),
        role="student",
        is_active=True,
        email_verified=False,
        email_verified_at=None,
        email_verification_required=False,
    )
    db.add(legacy_user)
    db.commit()

    # Legacy account must NOT be locked out
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy.student@dau.ac.in", "password": "LegacyPass123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # email_verified is NOT falsely asserted as True
    db.refresh(legacy_user)
    assert legacy_user.email_verified is False


def test_12_google_only_passwordless_accounts_retain_existing_behavior(client, db):
    """12. Google-only passwordless accounts retain existing behavior."""
    google_user = User(
        name="Google Campus User",
        email="google.user@dau.ac.in",
        password_hash=None,
        role="student",
        is_active=True,
        email_verified=True,
        email_verification_required=False,
    )
    db.add(google_user)
    db.commit()

    # Password login against passwordless Google account must fail with 401
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "google.user@dau.ac.in", "password": "AnyPassword123!"},
    )
    assert login_res.status_code == 401
    assert "invalid email or password" in login_res.json()["detail"].lower()


def test_13_resend_neutral_response_for_nonexistent_and_already_verified(client, db, mock_email):
    """Resend returns neutral response for nonexistent or already-verified accounts without dispatching email."""
    # 1. Nonexistent email
    res1 = client.post("/api/v1/auth/resend-verification", json={"email": "nobody@dau.ac.in"})
    assert res1.status_code == 200
    assert "If an account exists" in res1.json()["message"]
    assert len(mock_email.sent_emails) == 0

    # 2. Already verified user
    verified_user = User(
        name="Already Verified",
        email="already.verified@dau.ac.in",
        password_hash=get_password_hash("Pass123!"),
        role="student",
        is_active=True,
        email_verified=True,
        email_verification_required=True,
    )
    db.add(verified_user)
    db.commit()

    res2 = client.post("/api/v1/auth/resend-verification", json={"email": "already.verified@dau.ac.in"})
    assert res2.status_code == 200
    assert "If an account exists" in res2.json()["message"]
    # No unnecessary email sent to verified user
    assert len(mock_email.sent_emails) == 0


def test_14_resend_reports_error_when_email_provider_fails(client, db, mock_email):
    """Resend handles provider errors without falsely reporting success."""
    email = "resend.fail@dau.ac.in"
    client.post(
        "/api/v1/auth/register",
        json={"name": "Resend Fail", "email": email, "password": "Password123!"},
    )

    # Provider now fails
    mock_email.should_fail = True
    res = client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert res.status_code == 502
    assert "failed to deliver" in res.json()["detail"].lower()
