"""Pydantic schemas for hostel coverage gaps (S4-07)."""

from pydantic import BaseModel, ConfigDict


class CoverageGapItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hostel_id: int
    hostel_name: str
    open_count: int
