"""Admin endpoints for hostel staff coverage and gap detection (S4-07)."""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.user import User
from app.schemas.coverage import CoverageGapItem
from app.services.coverage_service import get_coverage_gaps

router = APIRouter(prefix="/admin", tags=["Admin Coverage"])


@router.get(
    "/coverage-gaps",
    response_model=List[CoverageGapItem],
    status_code=status.HTTP_200_OK,
    summary="List hostel coverage gaps",
    description="Returns hostels with open complaints and no assigned staff. Admin only.",
    responses={
        200: {"description": "List of hostels with open complaints and no assigned staff"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Administrator role required"},
    },
)
def list_coverage_gaps(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> List[CoverageGapItem]:
    return get_coverage_gaps(db)
