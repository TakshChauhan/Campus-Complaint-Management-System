from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.schemas.user import UserSafeResponse


class RegisterRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full student name",
        examples=["Aarav Patel"]
    )
    email: EmailStr = Field(
        ...,
        description="Valid student email address",
        examples=["aarav.patel@student.university.edu"]
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Account password (minimum 8 characters)",
        examples=["SecurePass123!"]
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_email_domain(cls, v: EmailStr) -> EmailStr:
        from app.core.config import settings
        lowered = str(v).strip().lower()
        allowed_domains = getattr(settings, "ALLOWED_EMAIL_DOMAINS", [])
        if allowed_domains and "*" not in allowed_domains:
            # Check domain matches
            domain = lowered.split("@")[-1] if "@" in lowered else ""
            if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
                domains_str = ", ".join(f"@{d}" for d in allowed_domains)
                raise ValueError(f"Registration restricted to official campus emails only ({domains_str})")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters long after trimming whitespace")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password cannot be entirely whitespace")
        if len(v.encode('utf-8')) > 72:
            raise ValueError("Password exceeds maximum length of 72 bytes")
        return v


class LoginRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="Registered user email",
        examples=["aarav.patel@student.university.edu"]
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Account password",
        examples=["SecurePass123!"]
    )

    model_config = ConfigDict(extra="forbid")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT Bearer access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token lifespan in seconds", examples=[86400])
    user: UserSafeResponse = Field(..., description="Safe authenticated user profile")


class GoogleAuthStartRequest(BaseModel):
    client_challenge: str = Field(
        ...,
        min_length=10,
        max_length=128,
        description="SHA-256 base64url challenge created by the frontend client for PKCE-style handoff verification",
        examples=["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"]
    )

    model_config = ConfigDict(extra="forbid")


class GoogleAuthStartResponse(BaseModel):
    authorization_url: str = Field(..., description="Google OAuth authorization URL to load in the secure popup")
    state: str = Field(..., description="Opaque transaction state identifier")


class GoogleExchangeRequest(BaseModel):
    ticket: str = Field(
        ...,
        min_length=10,
        max_length=128,
        description="Single-use handoff ticket delivered by popup callback postMessage",
        examples=["4f8b9e..."]
    )
    client_verifier: str = Field(
        ...,
        min_length=10,
        max_length=128,
        description="The matching client-side verifier whose S256 challenge was submitted in the start request",
        examples=["dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"]
    )

    model_config = ConfigDict(extra="forbid")


class GoogleAuthLinkRequiredDetail(BaseModel):
    detail: str = Field(
        "An account with this email already exists with password credentials. Please sign in with your email and password.",
        description="Actionable message instructing user to log in with password"
    )
    link_required: bool = Field(True, description="Flag indicating account linking is required")
