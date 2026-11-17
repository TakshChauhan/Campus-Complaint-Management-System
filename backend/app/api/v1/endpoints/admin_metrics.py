"""Administrator-only complaint metrics endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.user import User
from app.schemas.admin_metrics import (
    AdminMetricsSummary,
    HostelResolutionMetricsResponse,
)
from app.schemas.complaint import ResolutionMetricsResponse
from app.services.admin_metrics_service import get_admin_metrics_summary as build_admin_metrics_summary
from app.services.complaint_lifecycle_service import (
    calculate_hostel_resolution_metrics,
    calculate_rolling_resolution_metrics,
)

router = APIRouter(prefix="/admin/metrics", tags=["Admin Metrics"])


@router.get(
    "/resolution",
    response_model=ResolutionMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get rolling complaint resolution metrics",
    description=(
        "Returns resolution duration statistics for complaints resolved within "
        "the requested rolling window. Restricted to administrators."
    ),
    responses={
        200: {"description": "Rolling resolution metrics"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Administrator role required"},
        422: {"description": "Invalid query parameters"},
    },
)
def get_resolution_metrics(
    window_days: int = Query(30, gt=0, description="Rolling window size in days"),
    department_id: Optional[int] = Query(None, gt=0, description="Optional department ID filter"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ResolutionMetricsResponse:
    metrics = calculate_rolling_resolution_metrics(
        db,
        window_days=window_days,
        department_id=department_id,
    )
    return ResolutionMetricsResponse(**metrics)


@router.get(
    "/summary",
    response_model=AdminMetricsSummary,
    status_code=status.HTTP_200_OK,
    summary="Get admin complaint metrics summary",
    description=(
        "Returns total complaints, counts by lifecycle status, complaint counts "
        "for active departments, and rolling 30-day resolution metrics. "
        "Restricted to administrators."
    ),
    responses={
        200: {"description": "Admin dashboard complaint metrics"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Administrator role required"},
    },
)


def get_admin_metrics_summary(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminMetricsSummary:
    return AdminMetricsSummary(**build_admin_metrics_summary(db))


@router.get(
    "/resolution/by-hostel",
    response_model=HostelResolutionMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get rolling complaint resolution metrics grouped by hostel",
    description=(
        "Returns rolling resolution statistics grouped by the canonical hostel "
        "of each complaint's floor_id, plus unlocated Hostel-department complaints. "
        "Restricted to administrators."
    ),
    responses={
        200: {"description": "Rolling resolution metrics grouped by hostel"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Administrator role required"},
        422: {"description": "Invalid query parameters"},
    },
)
def get_hostel_resolution_metrics(
    window_days: int = Query(30, gt=0, description="Rolling window size in days"),
    department_id: Optional[int] = Query(None, gt=0, description="Optional department ID filter"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> HostelResolutionMetricsResponse:
    metrics = calculate_hostel_resolution_metrics(
        db,
        window_days=window_days,
        department_id=department_id,
    )
    return HostelResolutionMetricsResponse(**metrics)