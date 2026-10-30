"""Student residence and Hostel-staff verification schemas (API contract 7.3-7.5)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ResidenceStatus = Literal["pending", "verified", "rejected"]


class MyResidence(BaseModel):
    floor_id: int
    hostel: str
    wing: str
    floor: str
    status: ResidenceStatus
    remark: Optional[str] = None


class StaffResidenceItem(MyResidence):
    id: int
    student_id: int
    student_name: str
    student_email: str
    submitted_at: datetime
    decided_at: Optional[datetime] = None


class ResidenceUpdate(BaseModel):
    floor_id: int = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")


class ResidenceDecision(BaseModel):
    decision: Literal["approve", "reject"]
    remark: Optional[str] = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("remark")
    @classmethod
    def normalize_remark(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def require_reject_remark(self) -> "ResidenceDecision":
        if self.decision == "reject" and not self.remark:
            raise ValueError("A remark is required when rejecting a residence")
        return self
