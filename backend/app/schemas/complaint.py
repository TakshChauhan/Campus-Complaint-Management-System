from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComplaintCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Brief summary of the issue (3 to 120 characters)",
        examples=["Wi-Fi not working in hostel"]
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Detailed explanation of the complaint (10 to 2000 characters)",
        examples=["The Wi-Fi connection has been unavailable since this morning in Block B."]
    )
    department_id: int = Field(
        ...,
        gt=0,
        description="Positive integer referencing an active department",
        examples=[1]
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters")
        if len(cleaned) > 120:
            raise ValueError("Title cannot exceed 120 characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 10:
            raise ValueError("Description must contain at least 10 non-whitespace characters")
        if len(cleaned) > 2000:
            raise ValueError("Description cannot exceed 2000 characters")
        return cleaned


class ComplaintResponse(BaseModel):
    """Detailed complaint response returned upon creation and direct lookup."""
    id: int = Field(..., description="Unique generated complaint ID", examples=[101])
    title: str = Field(..., description="Complaint title", examples=["Wi-Fi not working in hostel"])
    description: str = Field(..., description="Detailed complaint description")
    department_id: int = Field(..., description="Target department ID", examples=[1])
    department_name: str = Field(..., description="Target department name", examples=["IT Services"])
    created_by_id: int = Field(..., description="ID of student who submitted complaint", examples=[1])
    status: str = Field(..., description="Current complaint workflow status", examples=["submitted"])
    created_at: datetime = Field(..., description="Timestamp when complaint was registered")

    model_config = ConfigDict(from_attributes=True)


class ComplaintListItem(BaseModel):
    """Summary item for personal complaint history listing.

    ``department_id`` and ``description_preview`` were added in Sprint 1 final
    (additive, backward compatible) so the history view can show a preview
    without a second request.
    """
    id: int = Field(..., description="Unique complaint ID", examples=[101])
    title: str = Field(..., description="Complaint title", examples=["Wi-Fi not working in hostel"])
    description_preview: str = Field(
        "",
        description="First 160 characters of the complaint description",
        examples=["The Wi-Fi connection has been unavailable since this morning in Block B."],
    )
    department_id: int = Field(..., description="Target department ID", examples=[1])
    department_name: str = Field(..., description="Target department name", examples=["IT Services"])
    status: str = Field(..., description="Current status", examples=["submitted"])
    created_at: datetime = Field(..., description="Submission timestamp")

    model_config = ConfigDict(from_attributes=True)
