
"""Request and response schemas for admin staff hostel assignments."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminStaffHostel(BaseModel):
    """Hostel assigned to a staff member."""

    id: int
    code: str
    name: str


class AdminStaffListItem(BaseModel):
    """Staff member and their assigned hostels."""

    id: int
    name: str
    email: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    hostels: List[AdminStaffHostel] = Field(default_factory=list)


class StaffHostelAssignmentUpdate(BaseModel):
    """Request to replace all hostel assignments for a staff member."""

    hostel_ids: List[int] = Field(
        ...,
        description="Complete list of hostel IDs to assign. An empty list clears all assignments.",
    )

    model_config = ConfigDict(extra="forbid")
