"""Hostel-department residence verification queue (API contract 7.4/7.5)."""

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.residence import ResidenceDecision, StaffResidenceItem
from app.services.residence_service import decide_residence, list_residences

router = APIRouter(prefix="/staff/residences", tags=["Staff Residences"])


@router.get(
    "",
    response_model=list[StaffResidenceItem],
    summary="List student residences awaiting or past Hostel verification",
    responses={403: {"description": "Only Hostel-department staff or administrators"}},
)
def read_residences(
    response: Response,
    status_filter: Literal["pending", "verified", "rejected"] = Query("pending", alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StaffResidenceItem]:
    items, total = list_residences(db, current_user, status_filter=status_filter, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post(
    "/{residence_id}/decision",
    response_model=StaffResidenceItem,
    summary="Approve or reject a pending student residence",
    responses={
        403: {"description": "Only Hostel-department staff or administrators"},
        404: {"description": "Residence not found"},
        409: {"description": "Residence is not pending"},
    },
)
def post_residence_decision(
    payload: ResidenceDecision,
    residence_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StaffResidenceItem:
    return decide_residence(db, current_user, residence_id, payload)
