import json
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Campus Complaint Management System (CCMS)"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database Configuration:
    # Local: sqlite:///./ccms.db (or local postgresql)
    # Cloud: postgresql+psycopg://... (e.g. Supabase, Neon, AWS RDS)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ccms_db"

    # Connection pooling parameters (bounded per worker)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Security & JWT
    JWT_SECRET: str = "dev-insecure-jwt-secret-key-change-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    ENABLE_API_DOCS: Optional[bool] = None

    # Email Domain Restriction for Password Registration:
    # in production, e.g. ["dau.ac.in", "daiict.ac.in"]
    ALLOWED_EMAIL_DOMAINS: Union[str, List[str]] = ["dau.ac.in", "daiict.ac.in", "student.campus.edu", "campus.edu"]

    # Google OAuth 2.0 / OpenID Connect (OIDC) Configuration
    GOOGLE_AUTH_ENABLED: bool = False
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_REDIRECT_URI: Optional[str] = None
    # Allowed Google Workspace hosted domains (matches signed 'hd' claim).
    # If empty, any verified Google account is eligible for account resolution.
    GOOGLE_ALLOWED_HOSTED_DOMAINS: Union[str, List[str]] = []
    # Dedicated symmetric key for server-side encryption of sensitive transaction data (PKCE verifier)
    GOOGLE_OAUTH_ENCRYPTION_KEY: Optional[str] = None
    GOOGLE_OAUTH_STATE_EXPIRE_SECONDS: int = 300  # 5 minutes
    GOOGLE_OAUTH_TICKET_EXPIRE_SECONDS: int = 60   # 1 minute

    # Optional Development / Demo User Seeding (STRICTLY FOR DEVELOPMENT/TESTING)
    ALLOW_DEMO_SEEDING: bool = False
    DEV_ADMIN_EMAIL: str = "admin@campus.edu"
    DEV_ADMIN_PASSWORD: str = "AdminSecret123!"
    DEV_STAFF_EMAIL: str = "staff.it@campus.edu"
    DEV_STAFF_PASSWORD: str = "StaffSecret123!"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("ALLOWED_EMAIL_DOMAINS", mode="before")
    @classmethod
    def assemble_allowed_email_domains(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [d.strip().lower().lstrip("@") for d in v.split(",") if d.strip()]
        if isinstance(v, list):
            return [str(d).strip().lower().lstrip("@") for d in v if str(d).strip()]
        return v

    @field_validator("GOOGLE_ALLOWED_HOSTED_DOMAINS", mode="before")
    @classmethod
    def assemble_google_allowed_domains(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [d.strip().lower().lstrip("@") for d in v.split(",") if d.strip()]
        if isinstance(v, list):
            return [str(d).strip().lower().lstrip("@") for d in v if str(d).strip()]
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip().startswith("[") and v.strip().endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql+psycopg2://"):
            return v.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @model_validator(mode="after")
    def validate_security(self) -> 'Settings':
        if self.ENABLE_API_DOCS is None:
            self.ENABLE_API_DOCS = self.ENVIRONMENT in ["development", "testing"]

        # Validate Google OAuth configuration if enabled
        if self.GOOGLE_AUTH_ENABLED:
            if not self.GOOGLE_OAUTH_CLIENT_ID or not self.GOOGLE_OAUTH_CLIENT_ID.strip():
                raise ValueError("GOOGLE_AUTH_ENABLED is True but GOOGLE_OAUTH_CLIENT_ID is not configured")
            if not self.GOOGLE_OAUTH_CLIENT_SECRET or not self.GOOGLE_OAUTH_CLIENT_SECRET.strip():
                raise ValueError("GOOGLE_AUTH_ENABLED is True but GOOGLE_OAUTH_CLIENT_SECRET is not configured")
            if not self.GOOGLE_OAUTH_REDIRECT_URI or not self.GOOGLE_OAUTH_REDIRECT_URI.strip():
                raise ValueError("GOOGLE_AUTH_ENABLED is True but GOOGLE_OAUTH_REDIRECT_URI is not configured")
            if not (self.GOOGLE_OAUTH_REDIRECT_URI.startswith("http://") or self.GOOGLE_OAUTH_REDIRECT_URI.startswith("https://")):
                raise ValueError("GOOGLE_OAUTH_REDIRECT_URI must be an absolute HTTP or HTTPS URL")

        # Non-development restrictions
        if self.ENVIRONMENT not in ["development", "testing"]:
            if self.JWT_SECRET == "dev-insecure-jwt-secret-key-change-in-production-min-32-chars":
                raise ValueError("Default development JWT secret cannot be used outside development/testing environments")
            if len(self.JWT_SECRET) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters long in non-development environments")
            if self.DEBUG:
                raise ValueError("DEBUG must be False in non-development environments")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Wildcard '*' CORS origin is not permitted in non-development environments")
            if self.ALLOW_DEMO_SEEDING:
                raise ValueError("ALLOW_DEMO_SEEDING must never be enabled in non-development environments")

            # Production database TLS enforcement for PostgreSQL
            if self.DATABASE_URL.startswith("postgresql"):
                lower_url = self.DATABASE_URL.lower()
                has_tls = (
                    "sslmode=require" in lower_url
                    or "sslmode=verify-full" in lower_url
                    or "sslmode=verify-ca" in lower_url
                )
                if not has_tls:
                    raise ValueError(
                        "Production PostgreSQL connections require explicit TLS enforcement (e.g. sslmode=require, verify-ca, or verify-full in DATABASE_URL)"
                    )

        return self


settings = Settings()
