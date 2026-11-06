"""Hostel publication moderation for admins and Hostel-department staff (API contract 7.11).

The /hmc paths are kept from Sprint 3 so existing clients do not break. Since
S4-09 the HMC group, audience and moderator-designation routes are removed.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated
from app.models.user import User
from app.schemas.public_feed import (
    FeedReviewQueueItem, FeedReviewRequest, FeedReviewResult, ModerationActionResult, UnpublishRequest,
)
from app.services.public_feed_service import (
    list_hmc_publication_review_queue, review_hmc_publication, unpublish_hmc_complaint,
)

router = APIRouter(prefix="/hmc", tags=["Hostel Publication Moderation"])
PathId = Annotated[int, Path(gt=0, le=2_147_483_647)]


@router.get("/publication-requests", response_model=list[FeedReviewQueueItem],
            summary="List pending hostel publication requests (Hostel staff/admins)",
            description="Hostel-department staff see located requests; admins also see unmapped ones. Full descriptions and reporter identity are internal-only.")
def read_publication_requests(response: Response,
    department_id: int | None = Query(None, gt=0, description="Optional department filter"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[FeedReviewQueueItem]:
    items, total = list_hmc_publication_review_queue(db, current_user,
        department_id=department_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/publication-requests/{complaint_id}/decision", response_model=FeedReviewResult,
             summary="Approve or reject a hostel publication request")
def post_publication_decision(payload: FeedReviewRequest, complaint_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> FeedReviewResult:
    return review_hmc_publication(db, current_user, complaint_id, payload)


@router.post("/complaints/{complaint_id}/unpublish", response_model=ModerationActionResult,
             summary="Remove a currently published complaint from feeds")
def post_unpublish(payload: UnpublishRequest, complaint_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> ModerationActionResult:
    complaint = unpublish_hmc_complaint(db, current_user, complaint_id, payload.note)
    return ModerationActionResult(complaint_id=complaint.id,
        publication_status=complaint.publication_status,
        message="Complaint unpublished. The moderation action was recorded in the audit trail.")
