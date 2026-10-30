"""Canonical hostel location tree (API contract 7.2)."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated
from app.models.user import User
from app.schemas.location import HostelNode
from app.services.location_service import list_active_hostel_tree

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get(
    "/hostels",
    response_model=List[HostelNode],
    summary="List active hostels with their active wings and floors",
    responses={401: {"description": "Missing or invalid bearer token"}},
)
def read_hostel_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated),
) -> List[HostelNode]:
    return list_active_hostel_tree(db)
