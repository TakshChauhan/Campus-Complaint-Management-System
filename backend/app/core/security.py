import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, Optional
import bcrypt
from cryptography.fernet import Fernet
import jwt

from app.core.config import settings


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt. Rejects input exceeding 72 UTF-8 bytes."""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise ValueError("Password exceeds 72 UTF-8 bytes limit for bcrypt")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: Optional[str], hashed_password: Optional[str]) -> bool:
    """Verify a plaintext password against a bcrypt hash. Safely returns False if input exceeds 72 bytes or if hash is None."""
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")
        if len(pwd_bytes) > 72:
            return False
        return bcrypt.checkpw(
            pwd_bytes,
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    subject: str,
    claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if claims:
        payload.update(claims)

    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token requiring sub, iat, and exp."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return payload
    except jwt.PyJWTError:
        return None


def hash_token(token: str) -> str:
    """Compute SHA-256 hex digest for indexing and storing opaque tokens/states."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def calculate_pkce_challenge(verifier: str) -> str:
    """Calculate S256 code_challenge from code_verifier according to RFC 7636."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_pkce_challenge(verifier: str, challenge: str) -> bool:
    """Validate that SHA-256 base64url of verifier matches expected challenge using constant-time comparison."""
    if not verifier or not challenge:
        return False
    calculated = calculate_pkce_challenge(verifier)
    return hmac.compare_digest(calculated, challenge)


def _get_fernet_cipher() -> Fernet:
    """Obtain Fernet cipher using GOOGLE_OAUTH_ENCRYPTION_KEY or a derived key from JWT_SECRET."""
    if settings.GOOGLE_OAUTH_ENCRYPTION_KEY and len(settings.GOOGLE_OAUTH_ENCRYPTION_KEY.strip()) >= 32:
        raw_key = settings.GOOGLE_OAUTH_ENCRYPTION_KEY.strip().encode("utf-8")
        # Ensure 32-byte urlsafe base64 key
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw_key).digest())
    else:
        # Fallback for development/testing: derive key from server secret
        derived = base64.urlsafe_b64encode(hashlib.sha256(b"oauth_state_secret_derivation:" + settings.JWT_SECRET.encode("utf-8")).digest())
    return Fernet(derived)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt sensitive transaction data using authenticated Fernet encryption."""
    cipher = _get_fernet_cipher()
    return cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt sensitive transaction data using authenticated Fernet encryption."""
    cipher = _get_fernet_cipher()
    return cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8")
