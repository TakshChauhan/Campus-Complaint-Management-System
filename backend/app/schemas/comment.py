"""Request and response schemas for complaint comments (S5-05)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMMENT_BODY_MAX_LENGTH = 1000


class CommentCreate(BaseModel):
    """A new comment. The body is stripped; it must then be 1–1000 characters."""

    body: str = Field(
        ...,
        description="Comment text, 1–1000 characters after trimming whitespace",
        examples=["Is there an update on when the tap will be fixed?"],
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Comment cannot be blank.")
        if len(cleaned) > COMMENT_BODY_MAX_LENGTH:
            raise ValueError(
                f"Comment cannot exceed {COMMENT_BODY_MAX_LENGTH} characters."
            )
        return cleaned


class CommentOut(BaseModel):
    """One comment as shown to the student owner or in-scope staff.

    Never carries the author's email or user id.
    """

    id: int
    body: str
    created_at: datetime
    author_role: Literal["student", "staff", "admin"]
    author_name: str
    is_mine: bool
