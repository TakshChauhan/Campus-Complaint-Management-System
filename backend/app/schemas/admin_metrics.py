"""Response schemas for administrator complaint metrics."""

from typing import Literal, List, Optional

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


class ResolutionDurationStats(BaseModel):
    """Common duration statistics returned by the rolling resolution services."""

    resolved_count: int = Field(..., ge=0, description="Number of resolved complaints in the rolling window")
    average_resolution_hours: Optional[float] = Field(None, description="Average resolution duration in hours")
    average_resolution_days: Optional[float] = Field(None, description="Average resolution duration in days")
    median_resolution_hours: Optional[float] = Field(None, description="Median resolution duration in hours")
    min_resolution_hours: Optional[float] = Field(None, description="Shortest resolution duration in hours")
    max_resolution_hours: Optional[float] = Field(None, description="Longest resolution duration in hours")

    model_config = ConfigDict(from_attributes=True)


class HostelResolutionMetricsItem(ResolutionDurationStats):
    """Resolution statistics for one hostel."""

    hostel_id: int = Field(..., gt=0, description="Canonical hostel ID")
    hostel_code: str = Field(..., description="Canonical hostel code")
    hostel_name: str = Field(..., description="Canonical hostel name")
    is_active: bool = Field(..., description="Whether the hostel is currently active")


class HostelResolutionMetricsResponse(BaseModel):
    """Rolling resolution statistics grouped by hostel, plus unlocated Hostel complaints."""

    window_days: int = Field(..., gt=0, description="Rolling window size in days")
    department_id: Optional[int] = Field(None, gt=0, description="Optional department filter")
    hostels: List[HostelResolutionMetricsItem] = Field(
        ..., description="Active hostels plus inactive hostels with resolved complaints in the window"
    )
    unlocated: ResolutionDurationStats = Field(
        ..., description="Resolved Hostel-department complaints without a canonical floor_id"
    )

    model_config = ConfigDict(from_attributes=True)
