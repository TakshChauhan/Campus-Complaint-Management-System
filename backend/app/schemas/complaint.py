from datetime import datetime
from typing import Optional
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

    is_public: bool = Field(default=False)
    floor_id: Optional[int] = Field(default=None, gt=0)
    hostel: Optional[str] = Field(default=None, max_length=100)
    wing: Optional[str] = Field(default=None, max_length=50)
    floor: Optional[str] = Field(default=None, max_length=20)

    model_config = ConfigDict(extra="forbid")

    @field_validator("hostel", "wing", "floor")
    @classmethod
    def normalize_location(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

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


class ComplaintLocation(BaseModel):
    hostel: str
    wing: str
    floor: str


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
    is_public: bool = False
    location: Optional[ComplaintLocation] = None
    hostel: Optional[str] = None
    wing: Optional[str] = None
    floor: Optional[str] = None
    reopen_count: int = 0
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

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


class PublicComplaintFeedItem(BaseModel):
    """Privacy-conscious representation of a complaint in the public feed."""
    id: int = Field(..., description="Unique complaint ID", examples=[101])
    title: str = Field(..., description="Complaint title", examples=["Wi-Fi not working in hostel"])
    description: str = Field(..., description="Detailed description")
    department_id: int = Field(..., description="Target department ID", examples=[1])
    department_name: str = Field(..., description="Target department name", examples=["IT Services"])
    status: str = Field(..., description="Current status", examples=["submitted"])
    is_public: bool = Field(True, description="Public status")
    hostel: Optional[str] = Field(None, description="Hostel building if applicable")
    wing: Optional[str] = Field(None, description="Wing if applicable")
    floor: Optional[str] = Field(None, description="Floor if applicable")
    reopen_count: int = Field(0, description="Number of times reopened")
    created_at: datetime = Field(..., description="Submission timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    resolved_at: Optional[datetime] = Field(None, description="Resolution timestamp")

    model_config = ConfigDict(from_attributes=True)


class ComplaintReopenRequest(BaseModel):
    """Request schema for student reopening a resolved complaint."""
    remark: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional student explanation for reopening the complaint",
        examples=["The internet issue returned after two days."],
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                return None
            if len(cleaned) > 2000:
                raise ValueError("Remark cannot exceed 2000 characters")
            return cleaned
        return None


class ComplaintReopenResponse(BaseModel):
    """Minimal lifecycle fields returned after a student reopens a complaint."""
    id: int = Field(..., description="Unique complaint ID")
    status: str = Field(..., description="Current complaint status; successful reopen returns 'reopened'")
    reopen_count: int = Field(..., description="Number of reopens used by this complaint")
    updated_at: datetime = Field(..., description="Timestamp of the reopen operation")
    resolved_at: Optional[datetime] = Field(None, description="Resolution timestamp; null while reopened")

    model_config = ConfigDict(from_attributes=True)


class ResolutionMetricsResponse(BaseModel):
    """Rolling resolution metrics and duration statistics."""
    window_days: int = Field(..., description="Rolling window size in days", examples=[30])
    department_id: Optional[int] = Field(None, description="Scoped department ID if filtered", examples=[1])
    resolved_count: int = Field(..., description="Number of resolved complaints within the window", examples=[12])
    average_resolution_hours: Optional[float] = Field(None, description="Average time to resolution in hours", examples=[24.5])
    average_resolution_days: Optional[float] = Field(None, description="Average time to resolution in days", examples=[1.02])
    median_resolution_hours: Optional[float] = Field(None, description="Median time to resolution in hours", examples=[18.0])
    min_resolution_hours: Optional[float] = Field(None, description="Shortest resolution time in hours", examples=[2.5])
    max_resolution_hours: Optional[float] = Field(None, description="Longest resolution time in hours", examples=[72.0])

    model_config = ConfigDict(from_attributes=True)
