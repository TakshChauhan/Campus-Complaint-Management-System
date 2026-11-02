"""Response schemas for administrator complaint metrics."""

from typing import Literal, List

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.complaint import ResolutionMetricsResponse


ComplaintLifecycleStatus = Literal["submitted", "in_progress", "resolved", "reopened"]


class StatusCountItem(BaseModel):
    """Complaint count for one lifecycle status."""

    status: ComplaintLifecycleStatus = Field(..., description="Complaint lifecycle status")
    count: int = Field(..., ge=0, description="Number of complaints in this status")


class DepartmentCountItem(BaseModel):
    """Complaint count for an active department."""

    department_id: int = Field(..., gt=0, description="Unique department ID")
    department_name: str = Field(..., description="Department name")
    count: int = Field(..., ge=0, description="Number of complaints assigned to the department")


class AdminMetricsSummary(BaseModel):
    """Aggregated complaint statistics and rolling resolution metrics for the admin dashboard."""

    total_complaints: int = Field(..., ge=0, description="Total number of complaint records")
    status_counts: List[StatusCountItem] = Field(..., description="Counts for all complaint lifecycle statuses")
    department_counts: List[DepartmentCountItem] = Field(..., description="Counts for active departments, including zero-count departments")
    resolution_metrics: ResolutionMetricsResponse = Field(..., description="Rolling resolution metrics for the default 30-day window")

    model_config = ConfigDict(from_attributes=True)
