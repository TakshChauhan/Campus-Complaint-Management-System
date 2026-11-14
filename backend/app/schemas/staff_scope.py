"""Schemas for the authenticated staff member's own hostel scope (S4-14)."""

from pydantic import BaseModel, ConfigDict


class StaffScopeHostel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class StaffHostelScopeResponse(BaseModel):
    """What the staff dashboard needs to limit its hostel filter and empty states.

    ``hostel_scoped`` is true only for Hostel-department staff, whose queues are
    limited to ``hostels``. For other departments it is false and ``hostels`` is
    always empty: their queues are limited by department only.
    """

    department_id: int
    hostel_scoped: bool
    hostels: list[StaffScopeHostel]
