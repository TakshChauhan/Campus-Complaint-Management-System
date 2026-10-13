from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DepartmentResponse(BaseModel):
    """Public department details returned for student selection."""
    id: int = Field(..., description="Unique department ID", examples=[1])
    name: str = Field(..., description="Department name", examples=["Hostel"])
    description: Optional[str] = Field(None, description="Department scope and details", examples=["Residential facilities and maintenance"])
    is_active: bool = Field(..., description="Operational status of the department", examples=[True])

    model_config = ConfigDict(from_attributes=True)


# Contract for advisory automated keyword-based department suggestions
class DepartmentSuggestionRequest(BaseModel):
    """Payload for requesting keyword-based advisory department suggestion based on complaint draft."""
    title: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Complaint draft title",
        examples=["Water leakage in room 204"]
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Complaint draft description",
        examples=["The bathroom tap has been continuously dripping since yesterday morning."]
    )

    @field_validator("title")
    @classmethod
    def validate_title_after_trim(cls, value: str) -> str:
        """Do not let surrounding whitespace bypass the title length rule."""
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description_after_trim(cls, value: str) -> str:
        """Enforce minimum meaningful length after removing surrounding space."""
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise ValueError("Description must contain at least 10 non-whitespace characters")
        return cleaned

    model_config = ConfigDict(extra="forbid")


class DepartmentSuggestionItem(BaseModel):
    """Individual department suggestion score and rationale."""
    department_id: int = Field(..., description="Suggested department ID", examples=[1])
    department_name: str = Field(..., description="Suggested department name", examples=["Hostel"])
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Heuristic confidence score between 0.0 and 1.0", examples=[0.92])
    rationale: Optional[str] = Field(None, description="Explanation for recommendation", examples=["Matched keywords relating to Hostel: tap, washroom"])


class DepartmentSuggestionResponse(BaseModel):
    """Keyword-based advisory suggestion contract. Students always retain authoritative final selection."""
    status: Literal["provisional_advisory", "uncertain", "error_fallback"] = Field(
        "provisional_advisory",
        description="Suggestion response status: provisional_advisory, uncertain, or error_fallback"
    )
    version: str = Field(..., description="Suggestion engine version")
    suggestions: List[DepartmentSuggestionItem] = Field(..., description="Ranked list of department suggestions")
    disclaimer: str = Field(
        "Automated keyword suggestions are strictly advisory. The complainant retains final authority to select their preferred department.",
        description="Advisory notice"
    )
