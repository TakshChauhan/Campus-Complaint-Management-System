"""Read-only view of the authenticated staff member's hostel scope (S4-14).

The staff dashboard uses this to list only the caller's assigned hostels in its
hostel filter and to show a clear empty state to Hostel staff with no hostels.
Access to complaints and residences is still enforced server-side by S4-04.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_staff
from app.models.hostel import Hostel
from app.models.user import User
from app.schemas.staff_scope import StaffHostelScopeResponse, StaffScopeHostel
from app.services.hostel_scope_service import get_staff_scope
from app.services.staff_service import require_assigned_department

router = APIRouter(prefix="/staff/me", tags=["Staff Scope"])


@router.get(
    "/hostels",
    response_model=StaffHostelScopeResponse,
    summary="List the hostels the authenticated staff member covers",
    responses={
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Not staff, no assigned department, or department inactive"},
    },
)
def read_my_hostel_scope(
    db: Session = Depends(get_db),
    current_staff: User = Depends(require_staff),
) -> StaffHostelScopeResponse:
    department_id = require_assigned_department(current_staff)
    scope = get_staff_scope(db, current_staff)

    if not scope.is_authorized:
        # Staff of an inactive department fail closed, matching apply_scope.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff account's department is not active.",
        )

    hostels: list[Hostel] = []
    if scope.is_hostel_staff and scope.hostel_ids:
        hostels = (
            db.query(Hostel)
            .filter(Hostel.id.in_(scope.hostel_ids), Hostel.is_active.is_(True))
            .order_by(Hostel.name, Hostel.id)
            .all()
        )

    return StaffHostelScopeResponse(
        department_id=department_id,
        hostel_scoped=scope.is_hostel_staff,
        hostels=[StaffScopeHostel.model_validate(hostel) for hostel in hostels],
    )
