"""Request and response schemas for staff complaint handling."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ComplaintStatusFilter = Literal["submitted", "in_progress", "resolved", "reopened"]
StaffUpdateStatus = Literal["in_progress", "resolved"]


class StaffComplaintQueueItem(BaseModel):
    """Privacy-conscious summary of a complaint in a staff member's queue."""

    id: int
    title: str
    description_preview: str
    department_id: int
    department_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    floor_id: int | None
    hostel: str | None
    wing: str | None
    floor: str | None


class StaffComplaintDetail(BaseModel):
    """Department-scoped details needed to process a complaint."""

    id: int
    title: str
    description: str
    department_id: int
    department_name: str
    status: str
    is_public: bool
    hostel: str | None
    wing: str | None
    floor: str | None
    reopen_count: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class StaffComplaintStatusUpdate(BaseModel):
    """A staff-authored status change; reopening is intentionally excluded."""

    status: StaffUpdateStatus = Field(
        ...,
        description="Staff may move a complaint to in_progress or resolved; reopening is not allowed here.",
    )
    remark: str = Field(..., min_length=1, max_length=2000, description="Required explanation for the status change")

    model_config = ConfigDict(extra="forbid")

    @field_validator("remark")
    @classmethod
    def validate_remark(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Remark must contain at least one non-whitespace character")
        if len(cleaned) > 2000:
            raise ValueError("Remark cannot exceed 2000 characters")
        return cleaned
