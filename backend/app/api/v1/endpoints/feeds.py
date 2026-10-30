"""Privacy-safe public complaint feeds (API contract 7.7, 7.8 and 7.10)."""
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated
from app.models.user import User
from app.schemas.public_feed import FeedItem, HostelFeedItem
from app.services.public_feed_service import get_feed_item, list_department_feed, list_hostel_feed

router = APIRouter(prefix="/feeds", tags=["Public Complaint Feeds"])
StatusFilter = Literal["submitted", "in_progress", "resolved", "reopened"]


@router.get(
    "/departments/{department_id}",
    response_model=list[FeedItem],
    summary="Browse published department-wide complaints of a non-Hostel department",
    description="Only published, non-location-specific complaints. No description, reporter identity or moderation details.",
    responses={
        400: {"description": "hostel_feed_required: use /feeds/hostel for the Hostel department"},
        404: {"description": "Department not found or inactive"},
    },
)
def read_department_feed(
    response: Response,
    department_id: int = Path(..., gt=0, le=2_147_483_647),
    status_filter: StatusFilter | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated),
) -> list[FeedItem]:
    items, total = list_department_feed(
        db, department_id=department_id, status_filter=status_filter, limit=limit, offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get(
    "/hostel",
    response_model=list[HostelFeedItem],
    summary="Browse HMC-scoped complaints for a verified HMC member or Hostel staff/admin",
    description=(
        "Students see only published complaints explicitly authorized for their verified HMC group "
        "and cannot select a hostel. Hostel-department staff and admins see all authorized items and "
        "may filter by hostel_id."
    ),
    responses={
        403: {"description": "residence_not_verified, hostel_selection_forbidden, or unauthorized staff"},
        404: {"description": "Hostel department missing/inactive, or hostel_not_found"},
    },
)
def read_hostel_feed(
    response: Response,
    hostel_id: int | None = Query(None, gt=0, le=2_147_483_647),
    status_filter: StatusFilter | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated),
) -> list[HostelFeedItem]:
    items, total = list_hostel_feed(
        db, current_user, hostel_id=hostel_id, status_filter=status_filter, limit=limit, offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get(
    "/items/{complaint_id}",
    response_model=HostelFeedItem,
    summary="View one feed item the caller is allowed to see",
    description="Repeats the feed access rules for a single complaint and never returns its description.",
    responses={404: {"description": "Not found or not visible to the caller"}},
)
def read_feed_item(
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated),
) -> HostelFeedItem:
    return get_feed_item(db, current_user, complaint_id)
