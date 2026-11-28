from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserSafeResponse(BaseModel):
    """Safe user profile response containing public identity and role information."""
    id: int = Field(..., description="Unique user identifier", examples=[1])
    name: str = Field(..., description="Full user name", examples=["Alex Student"])
    email: EmailStr = Field(..., description="User email address", examples=["alex.student@campus.edu"])
    role: str = Field(..., description="Assigned role: student, staff, or admin", examples=["student"])
    is_active: bool = Field(..., description="Whether user account is active", examples=[True])
    email_verified: bool = Field(False, description="Whether user email address has been verified", examples=[True])
    email_verified_at: Optional[datetime] = Field(None, description="Timestamp when email was verified", examples=[None])
    email_verification_required: bool = Field(False, description="Whether email verification is required for password login", examples=[True])
    google_linked: bool = Field(False, description="Whether Google OAuth account is linked to this user", examples=[True])
    department_id: Optional[int] = Field(None, description="Assigned department ID for staff", examples=[None])
    created_at: datetime = Field(..., description="Timestamp when account was created")
    message: Optional[str] = Field(None, description="Informational message regarding account state")

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256, description="Current account password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New account password (minimum 8 characters)",
        examples=["NewSecurePass123!"],
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password cannot be entirely whitespace")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password exceeds maximum length of 72 bytes")
        return v


class ChangePasswordResponse(BaseModel):
    message: str = Field("Password changed successfully.", description="Confirmation message")
