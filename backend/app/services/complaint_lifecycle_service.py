"""Integration placeholder for the shared complaint lifecycle service.

The lifecycle implementation (status transitions, atomic history writes,
resolution timestamps, and reopen semantics) is assigned to the lifecycle
service owner. This placeholder deliberately performs no database mutations.
Replace its implementation with the agreed shared service before enabling
staff status updates in an environment where the endpoint must be functional.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.staff import StaffComplaintDetail, StaffComplaintStatusUpdate


def update_department_complaint_status(
    db: Session,
    staff: User,
    complaint_id: int,
    payload: StaffComplaintStatusUpdate,
) -> StaffComplaintDetail:
    """Reserved service interface; lifecycle implementation is not included here."""
    # These arguments document the contract the route expects; the placeholder
    # intentionally does not read or mutate the database.
    _ = (db, staff, complaint_id, payload)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Staff status updates are not enabled until the shared complaint "
            "lifecycle service is implemented and integrated."
        ),
    )
