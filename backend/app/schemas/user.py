from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
