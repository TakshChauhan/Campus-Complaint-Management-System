"""Request/response contracts for privacy-safe feeds and HMC moderation.

Feed DTOs follow API contract 7.1/7.10: no description, reporter identity or
moderation notes. Full descriptions and reporter identity appear only in the
internal moderation queue for admins and designated HMC moderators.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedItem(BaseModel):
    id: int
    title: str
    department_id: int
    department_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    reopen_count: int
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HostelFeedItem(FeedItem):
    # Resolved from the canonical floor; null only for legacy records.
    hostel: str | None = None
    wing: str | None = None
    floor: str | None = None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedReviewQueueItem(BaseModel):
    """Internal queue for explicitly designated HMC moderators/admins."""
    id: int
    title: str
    description: str
    department_id: int
    department_name: str
    status: str
    floor_id: int | None = None
    hostel: str | None = None
    wing: str | None = None
    floor: str | None = None
    responsible_hmc_group_id: int | None = None
    created_at: datetime
    publication_status: Literal["pending_review", "pending_mapping"]
    reporter_id: int
    reporter_name: str | None = None
    reporter_email: str | None = None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FeedReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)
    model_config = ConfigDict(extra="forbid")

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


def _required_reason(value: str) -> str:
    value = value.strip()
    if len(value) < 3:
        raise ValueError("A reason of at least 3 characters is required")
    return value


class UnpublishRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _required_reason(value)


class AudienceGrantRequest(BaseModel):
    """Explicitly share a published complaint with another group on the same floor level."""
    hmc_group_id: int = Field(gt=0)
    note: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _required_reason(value)


class AudienceRevokeRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(extra="forbid")

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return _required_reason(value)


class AudienceItem(BaseModel):
    hmc_group_id: int
    hmc_group_name: str
    source: Literal["responsible_group", "shared_floor"]
    decided_by_id: int
    created_at: datetime
    model_config = ConfigDict(extra="forbid")


class HMCGroupSummary(BaseModel):
    """Group configuration for moderators/admins; contains no student data."""
    id: int
    name: str
    hostel_id: int
    hostel_name: str
    floor_code: str
    floor_ids: list[int]
    is_active: bool
    is_valid: bool
    model_config = ConfigDict(extra="forbid")
