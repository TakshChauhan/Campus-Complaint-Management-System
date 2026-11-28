
"""Response schemas for administrator complaint metrics."""

from typing import Dict, Literal, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.complaint import ResolutionMetricsResponse

ComplaintLifecycleStatus = Literal["submitted", "in_progress", "resolved", "reopened"]

class StatusCountItem(BaseModel):
    """Complaint count for one lifecycle status."""

    status: ComplaintLifecycleStatus = Field(
        ..., description="Complaint lifecycle status"
    )
    count: int = Field(
        ..., ge=0, description="Number of complaints in this status"
    )

class DepartmentCountItem(BaseModel):
    """Complaint count for an active department."""

    department_id: int = Field(
        ..., gt=0, description="Unique department ID"
    )
    department_name: str = Field(..., description="Department name")
    count: int = Field(
        ..., ge=0,
        description="Number of complaints assigned to the department"
    )

class AdminMetricsSummary(BaseModel):
    """Aggregated complaint statistics and rolling resolution metrics."""

    total_complaints: int = Field(..., ge=0)
    status_counts: List[StatusCountItem]
    department_counts: List[DepartmentCountItem]
    resolution_metrics: ResolutionMetricsResponse

    model_config = ConfigDict(from_attributes=True)

class ResolutionDurationStats(BaseModel):
    """Common duration statistics returned by rolling resolution services."""

    resolved_count: int = Field(..., ge=0)
    average_resolution_hours: Optional[float] = None
    average_resolution_days: Optional[float] = None
    median_resolution_hours: Optional[float] = None
    min_resolution_hours: Optional[float] = None
    max_resolution_hours: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

class HostelResolutionMetricsItem(ResolutionDurationStats):
    """Resolution statistics for one hostel."""

    hostel_id: int = Field(..., gt=0)
    hostel_code: str
    hostel_name: str
    is_active: bool

class HostelResolutionMetricsResponse(BaseModel):
    """Rolling resolution statistics grouped by hostel."""

    window_days: int = Field(..., gt=0)
    department_id: Optional[int] = Field(None, gt=0)
    hostels: List[HostelResolutionMetricsItem]
    unlocated: ResolutionDurationStats

    model_config = ConfigDict(from_attributes=True)

class DepartmentFeedbackSummary(BaseModel):
    """Feedback rating summary for one department."""

    department_id: int = Field(..., gt=0)
    department_name: str
    count: int = Field(..., ge=0)
    average_rating: Optional[float] = None

class FeedbackMetricsResponse(BaseModel):
    """Overall and department-wise feedback rating summary."""

    count: int = Field(..., ge=0)
    average_rating: Optional[float] = None
    distribution: Dict[int, int]
    by_department: List[DepartmentFeedbackSummary]

    model_config = ConfigDict(from_attributes=True)
