"""Request/response contracts for privacy-safe student feeds and HMC moderation."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedComplaintItem(BaseModel):
    """Student feed projection: no description, reporter identity, or moderation data."""
    id: int
    title: str
    department_id: int
    department_name: str
    status: str
    affected_building_id: int | None = None
    affected_building_name: str | None = None
    affected_floor_id: int | None = None
    affected_floor_name: str | None = None
    affected_wing_id: int | None = None
    affected_wing_name: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedComplaintDetail(FeedComplaintItem):
    """Student-visible detail is intentionally the same privacy-safe projection."""
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedReviewQueueItem(BaseModel):
    """Internal queue for explicitly designated HMC moderators/admins."""
    id: int
    title: str
    description: str
    department_id: int
    department_name: str
    status: str
    affected_building_id: int | None = None
    affected_building_name: str | None = None
    affected_floor_id: int | None = None
    affected_floor_name: str | None = None
    affected_wing_id: int | None = None
    affected_wing_name: str | None = None
    created_at: datetime
    publication_status: Literal["pending_review", "pending_mapping"]
    reporter_id: int
    reporter_name: str | None = None
    reporter_email: str | None = None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)
    audience_group_ids: list[int] | None = Field(
        default=None, max_length=20,
        description="Required when approving a shared-floor complaint; identifies the exact authorized HMC groups.",
    )
    model_config = ConfigDict(extra="forbid")

    @field_validator("audience_group_ids")
    @classmethod
    def validate_audience_group_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(not isinstance(group_id, int) or group_id <= 0 for group_id in value):
            raise ValueError("Audience group IDs must be positive integers")
        if len(value) > 20 or len(value) != len(set(value)):
            raise ValueError("Audience group IDs must be unique and contain at most 20 entries")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 1000:
            raise ValueError("Review note cannot exceed 1000 characters")
        return value


class FeedReviewResult(BaseModel):
    id: int
    feed_review_status: Literal["approved", "rejected"]
    publication_status: Literal["published", "rejected"]
    feed_reviewed_at: datetime
    message: str
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedBuildingOption(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedFloorOption(BaseModel):
    id: int
    building_id: int
    building_name: str
    name: str
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedWingOption(BaseModel):
    id: int
    building_id: int
    building_name: str
    name: str
    floor_id: int
    floor_name: str
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedLocationCatalogue(BaseModel):
    buildings: list[FeedBuildingOption]
    floors: list[FeedFloorOption]
    wings: list[FeedWingOption]
    model_config = ConfigDict(extra="forbid")


class ResidenceVerificationRequest(BaseModel):
    building_id: int = Field(gt=0)
    floor_id: int = Field(gt=0)
    wing_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=1000)
    model_config = ConfigDict(extra="forbid")


class ModeratorAssignmentRequest(BaseModel):
    assigned: bool = True
    model_config = ConfigDict(extra="forbid")


class ModerationActionResult(BaseModel):
    complaint_id: int | None = None
    user_id: int | None = None
    hmc_group_id: int | None = None
    publication_status: str | None = None
    message: str
    model_config = ConfigDict(extra="forbid")


class UnpublishRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A reason of at least 3 characters is required")
        return value
