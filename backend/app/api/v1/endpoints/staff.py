"""Staff-only endpoints for department complaint handling."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_staff
from app.models.user import User
from app.schemas.staff import (
    ComplaintStatusFilter,
    StaffComplaintDetail,
    StaffComplaintQueueItem,
    StaffComplaintStatusUpdate,
)
from app.services.complaint_lifecycle_service import update_department_complaint_status
from app.services.staff_service import get_department_complaint, list_department_complaints

router = APIRouter(prefix="/staff/complaints", tags=["Staff Complaints"])


@router.get(
    "",
    response_model=list[StaffComplaintQueueItem],
    summary="List complaints assigned to the authenticated staff member's department",
    responses={403: {"description": "Staff account has no assigned department"}},
)
def read_department_complaints(
    response: Response,
    status_filter: Annotated[
        ComplaintStatusFilter | None,
        Query(alias="status", description="Optionally filter by complaint status"),
    ] = None,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of complaints to return"),
    offset: int = Query(0, ge=0, description="Number of matching complaints to skip"),
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_staff),
) -> list[StaffComplaintQueueItem]:
    items, total = list_department_complaints(
        db,
        current_staff,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get(
    "/{complaint_id}",
    response_model=StaffComplaintDetail,
    summary="View a complaint assigned to the authenticated staff member's department",
    responses={404: {"description": "Complaint not found in the staff member's department"}},
)
def read_department_complaint(
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_staff),
) -> StaffComplaintDetail:
    return get_department_complaint(db, current_staff, complaint_id)


@router.patch(
    "/{complaint_id}/status",
    response_model=StaffComplaintDetail,
    status_code=status.HTTP_200_OK,
    summary="Update a complaint's status with a required staff remark",
    responses={
        404: {"description": "Complaint not found in the staff member's department"},
        409: {"description": "The requested status transition is not allowed"},
    },
)
def patch_department_complaint_status(
    payload: StaffComplaintStatusUpdate,
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_staff),
) -> StaffComplaintDetail:
    # Keep out-of-department complaint IDs hidden before invoking the lifecycle service.

    get_department_complaint(db, current_staff, complaint_id)
    return update_department_complaint_status(db, current_staff, complaint_id, payload)
