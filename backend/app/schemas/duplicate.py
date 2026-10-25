"""Schemas for privacy-safe duplicate complaint suggestions."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DuplicateSuggestionRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=10, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Text is too short")
        return cleaned


class DuplicateSuggestionItem(BaseModel):
    id: int
    title: str
    department_id: int
    department_name: str
    status: str
    similarity_score: float = Field(ge=0, le=1)


class DuplicateSuggestionsResponse(BaseModel):
    matches: list[DuplicateSuggestionItem]
    threshold: float
    disclaimer: str
