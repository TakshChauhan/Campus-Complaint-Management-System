from app.core.security import verify_password
from app.models.user import User


def test_student_registration_success(client, db):
    payload = {
        "name": "Jane Doe",
        "email": "jane.doe@dau.ac.in",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Jane Doe"
    assert data["email"] == "jane.doe@dau.ac.in"
    assert data["role"] == "student"
    assert data["is_active"] is True
    assert "password" not in data
    assert "password_hash" not in data

    # Verify directly in database that password was hashed
    saved_user = db.query(User).filter(User.email == "jane.doe@dau.ac.in").first()
    assert saved_user is not None
    assert saved_user.password_hash != "StrongPassword123!"
    assert verify_password("StrongPassword123!", saved_user.password_hash)


def test_student_registration_daiict_domain_success(client, db):
    payload = {
        "name": "Rohan Shah",
        "email": "202101001@daiict.ac.in",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Rohan Shah"
    assert data["email"] == "202101001@daiict.ac.in"
    assert data["role"] == "student"


def test_student_registration_rejects_non_dau_email(client):
    payload = {
        "name": "External User",
        "email": "outsider@gmail.com",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert "dau.ac.in" in response.text


def test_student_registration_duplicate_email(client, db):
    email = "alice@dau.ac.in"
    # First registration
    res1 = client.post("/api/v1/auth/register", json={"name": "Alice", "email": email, "password": "Password123!"})
    assert res1.status_code == 201

    # Duplicate registration
    res2 = client.post("/api/v1/auth/register", json={"name": "Another Alice", "email": email, "password": "NewPassword123!"})
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_student_registration_rejects_injected_role(client):
    payload = {
        "name": "Attacker",
        "email": "attacker@dau.ac.in",
        "password": "Password123!",
        "role": "admin",  # forbidden field
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_student_registration_validation_short_password(client):
    payload = {
        "name": "Short Pass User",
        "email": "short@student.campus.edu",
        "password": "123",  # < 8 chars
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_student_registration_validation_blank_name(client):
    payload = {
        "name": "   ",
        "email": "blankname@student.campus.edu",
        "password": "ValidPassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_login_success(client, student_user):
    payload = {
        "email": student_user.email,
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["email"] == student_user.email
    assert data["user"]["role"] == "student"
    assert "password_hash" not in data["user"]


def test_login_invalid_password(client, student_user):
    payload = {
        "email": student_user.email,
        "password": "WrongPassword999!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_nonexistent_email(client):
    payload = {
        "email": "doesnotexist@campus.edu",
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    # Generic error without revealing email existence
    assert "invalid email or password" in response.json()["detail"].lower()


def test_get_current_user_me_success(client, student_user, student_headers):
    response = client.get("/api/v1/users/me", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == student_user.id
    assert data["name"] == student_user.name
    assert data["email"] == student_user.email
    assert data["role"] == "student"
    assert "password_hash" not in data


def test_get_current_user_me_unauthorized(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_get_current_user_me_invalid_token(client):
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401


def test_deactivated_user_cannot_login(client, db, student_user):
    student_user.is_active = False
    db.commit()

    payload = {
        "email": student_user.email,
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 403


def test_login_jwt_payload_minimization(client, student_user):
    """Ensure newly issued JWTs minimize claims to sub, iat, exp, and optional role, without personal data."""
    import jwt
    from app.core.config import settings

    payload = {
        "email": student_user.email,
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    token = response.json()["access_token"]

    unverified = jwt.decode(token, options={"verify_signature": False})
    assert "sub" in unverified
    assert unverified["sub"] == str(student_user.id)
    assert "iat" in unverified
    assert "exp" in unverified
    assert "role" in unverified
    assert unverified["role"] == "student"

    # Personal data must NOT be present in the token payload
    assert "email" not in unverified
    assert "name" not in unverified


def test_login_whitespace_only_password_returns_generic_401(client, student_user):
    """Whitespace-only password at login must return 401 generic failure rather than 422 policy disclosure."""
    payload = {
        "email": student_user.email,
        "password": "   ",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_over_72_byte_password_returns_generic_401(client, student_user):
    """Over-72-byte password at login must return 401 generic failure rather than 422 policy disclosure."""
    payload = {
        "email": student_user.email,
        "password": "P" * 80,
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_nonexistent_email_exercises_password_verification(client, monkeypatch):
    """Unknown email requests must still exercise password verification against dummy hash."""
    from app.services import auth_service

    called = []
    original_verify = auth_service.verify_password

    def spy_verify(plain, hashed):
        called.append((plain, hashed))
        return original_verify(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", spy_verify)

    payload = {
        "email": "ghost.user@campus.edu",
        "password": "SomeAttemptPassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert len(called) == 1
    assert called[0][1] == auth_service.DUMMY_BCRYPT_HASH


def test_password_hash_rejects_over_72_bytes():
    """get_password_hash must reject inputs exceeding 72 UTF-8 bytes to avoid silent bcrypt truncation."""
    import pytest
    from app.core.security import get_password_hash

    long_password = "a" * 73
    with pytest.raises(ValueError, match="Password exceeds 72 UTF-8 bytes limit"):
        get_password_hash(long_password)


def test_verify_password_returns_false_on_over_72_bytes(student_user):
    """verify_password must safely return False for inputs exceeding 72 bytes."""
    from app.core.security import verify_password

    long_password = "a" * 75
    assert verify_password(long_password, student_user.password_hash) is False


def test_jwt_missing_required_claims(client, student_user):
    """JWT decoding must reject tokens missing sub, iat, or exp."""
    import jwt
    import time
    from app.core.config import settings

    now = int(time.time())

    # Missing sub
    no_sub = jwt.encode({"iat": now, "exp": now + 3600}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    r1 = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {no_sub}"})
    assert r1.status_code == 401

    # Missing iat
    no_iat = jwt.encode({"sub": str(student_user.id), "exp": now + 3600}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    r2 = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {no_iat}"})
    assert r2.status_code == 401

    # Missing exp
    no_exp = jwt.encode({"sub": str(student_user.id), "iat": now}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    r3 = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {no_exp}"})
    assert r3.status_code == 401


def test_jwt_expired_token(client, student_user):
    """Expired JWT must return 401 Unauthorized."""
    import jwt
    import time
    from app.core.config import settings

    past = int(time.time()) - 3600
    expired = jwt.encode(
        {"sub": str(student_user.id), "iat": past - 3600, "exp": past},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401


def test_jwt_alg_none_and_invalid_signature(client, student_user):
    """Tokens signed with alg=none or wrong secret must be rejected with 401."""
    import jwt
    import time
    from app.core.config import settings

    now = int(time.time())
    payload = {"sub": str(student_user.id), "iat": now, "exp": now + 3600}

    # Wrong secret
    wrong_secret_token = jwt.encode(payload, "wrong-secret-key-32-chars-long-abc!", algorithm="HS256")
    res1 = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {wrong_secret_token}"})
    assert res1.status_code == 401

    # Malformed token
    res2 = client.get("/api/v1/users/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert res2.status_code == 401


def test_rate_limiter_on_auth_login(client, student_user):
    """In-memory rate limiter must trigger HTTP 429 with Retry-After when requests exceed limit."""
    from app.core.rate_limit import auth_rate_limiter

    # Lower limit temporarily for rapid test verification
    original_limit = auth_rate_limiter.requests_limit
    try:
        auth_rate_limiter.requests_limit = 3
        auth_rate_limiter.reset()

        payload = {"email": student_user.email, "password": "Password123!"}

        for _ in range(3):
            res = client.post("/api/v1/auth/login", json=payload)
            assert res.status_code == 200

        # 4th request must exceed limit
        res4 = client.post("/api/v1/auth/login", json=payload)
        assert res4.status_code == 429
        assert "rate limit exceeded" in res4.json()["detail"].lower()
        assert "retry-after" in res4.headers
        assert int(res4.headers["retry-after"]) > 0
    finally:
        auth_rate_limiter.requests_limit = original_limit
        auth_rate_limiter.reset()
