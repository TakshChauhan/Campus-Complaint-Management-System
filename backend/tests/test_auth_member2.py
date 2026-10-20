"""Member 2 security regression tests for existing Sprint 1 authentication."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.rate_limit import InMemoryRateLimiter


def _request(host: str = "192.0.2.8"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_rate_limiter_rejects_requests_after_limit():
    limiter = InMemoryRateLimiter(requests_limit=2, window_seconds=60)
    for _ in range(2):
        limiter.check(_request())
    with pytest.raises(HTTPException) as exc:
        limiter.check(_request())
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_rate_limiter_tracks_addresses_independently():
    limiter = InMemoryRateLimiter(requests_limit=1, window_seconds=60)
    limiter.check(_request("192.0.2.8"))
    limiter.check(_request("192.0.2.9"))
    with pytest.raises(HTTPException) as exc:
        limiter.check(_request("192.0.2.8"))
    assert exc.value.status_code == 429
    limiter.reset()
    limiter.check(_request("192.0.2.8"))


def test_concurrent_requests_cannot_bypass_in_process_limit():
    limiter = InMemoryRateLimiter(requests_limit=7, window_seconds=60)

    def attempt(_):
        try:
            limiter.check(_request())
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(attempt, range(40)))
    assert results.count(200) == 7
    assert results.count(429) == 33


def test_registration_requires_explicit_login(client, db, monkeypatch):
    """Registration requires email verification before password login."""
    from app.models.verification_token import EmailVerificationToken
    from app.services import auth_service

    email = "flow.student@dau.ac.in"
    password = "StrongPassword123!"

    # Capture the verification token instead of sending a real email
    sent_emails = []

    class FakeEmailSender:
        def send_verification_email(self, to_email, name, token):
            sent_emails.append(token)

    monkeypatch.setattr(
        auth_service,
        "get_email_sender",
        lambda: FakeEmailSender(),
    )

    # Register a new student
    res = client.post(
        "/api/v1/auth/register",
        json={"name": "Flow Student", "email": email, "password": password},
    )

    assert res.status_code == 201
    data = res.json()
    assert data["email"] == email
    assert data["role"] == "student"
    assert data["email_verified"] is False
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert "set-cookie" not in res.headers

    # Registration alone must not grant access
    assert client.get("/api/v1/users/me").status_code == 401

    # Login should fail until the email is verified
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 403

    # The registration email should contain a verification token
    assert len(sent_emails) == 1
    token = sent_emails[0]

    # Simulate clicking the verification link
    verify = client.post(
        "/api/v1/auth/verify-email",
        json={"token": token},
    )
    assert verify.status_code == 200

    # Login should now succeed
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200

    token = login.json()["access_token"]
    me = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email

def test_passwordless_google_account_cannot_use_password_login(client, db):
    """Google-only users have no local password and must not pass password login."""
    from app.models.user import User
    user = User(name="Google Student", email="google.only@dau.ac.in", password_hash=None,
                role="student", is_active=True, email_verified=True)
    db.add(user)
    db.commit()
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "AnyPassword123!"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
