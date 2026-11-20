"""Complaint comment routes (S5-05, API contract 7.16).

Two route families share one service:

* ``/complaints/{id}/comments``        — the student who owns the complaint
* ``/staff/complaints/{id}/comments``  — staff of the handling department,
  limited to their assigned hostels for Hostel staff (S4-04)

Every other signed-in user gets 404, and so does a complaint that does not
exist. Comments are append-only, so there is no PATCH or DELETE.
"""

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentOut
from app.services.comment_service import (
    add_owner_comment,
    add_staff_comment,
    list_owner_comments,
    list_staff_comments,
)

owner_router = APIRouter(prefix="/complaints", tags=["Complaint Comments"])
staff_router = APIRouter(prefix="/staff/complaints", tags=["Complaint Comments"])

_COMPLAINT_ID = Path(..., gt=0, le=2_147_483_647)
_LIMIT = Query(50, ge=1, le=100, description="Maximum number of comments to return")
_OFFSET = Query(0, ge=0, description="Number of comments to skip")

_LIST_RESPONSES = {
    401: {"description": "Missing or invalid bearer token"},
    404: {"description": "Complaint not found or not visible to the caller"},
}
_POST_RESPONSES = {
    **_LIST_RESPONSES,
    422: {"description": "Body is blank or longer than 1000 characters"},
}


@owner_router.get(
    "/{complaint_id}/comments",
    response_model=list[CommentOut],
    summary="List comments on your own complaint, oldest first",
    responses=_LIST_RESPONSES,
)
def read_owner_comments(
    response: Response,
    complaint_id: int = _COMPLAINT_ID,
    limit: int = _LIMIT,
    offset: int = _OFFSET,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommentOut]:
    items, total = list_owner_comments(db, current_user, complaint_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@owner_router.post(
    "/{complaint_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to your own complaint",
    responses=_POST_RESPONSES,
)
def create_owner_comment(
    payload: CommentCreate,
    complaint_id: int = _COMPLAINT_ID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommentOut:
    return add_owner_comment(db, current_user, complaint_id, payload.body)


@staff_router.get(
    "/{complaint_id}/comments",
    response_model=list[CommentOut],
    summary="List comments on a complaint in your department and hostel scope",
    responses=_LIST_RESPONSES,
)
def read_staff_comments(
    response: Response,
    complaint_id: int = _COMPLAINT_ID,
    limit: int = _LIMIT,
    offset: int = _OFFSET,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommentOut]:
    items, total = list_staff_comments(db, current_user, complaint_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@staff_router.post(
    "/{complaint_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a complaint in your department and hostel scope",
    responses=_POST_RESPONSES,
)
def create_staff_comment(
    payload: CommentCreate,
    complaint_id: int = _COMPLAINT_ID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommentOut:
    return add_staff_comment(db, current_user, complaint_id, payload.body)
