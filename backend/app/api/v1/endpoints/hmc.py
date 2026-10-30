"""HMC publication moderation for admins and designated HMC-group moderators.

Department staff membership alone grants none of these actions. Only GET, POST
and PATCH are used so the existing CORS policy applies unchanged.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated
from app.models.user import User
from app.schemas.public_feed import (
    AudienceGrantRequest, AudienceItem, AudienceRevokeRequest, FeedReviewQueueItem, FeedReviewRequest,
    FeedReviewResult, HMCGroupSummary, ModerationActionResult, ModeratorAssignmentRequest, UnpublishRequest,
)
from app.services.public_feed_service import (
    assign_hmc_moderator, grant_shared_floor_audience, list_complaint_audiences, list_hmc_groups,
    list_hmc_publication_review_queue, review_hmc_publication, revoke_shared_floor_audience,
    unpublish_hmc_complaint,
)

router = APIRouter(prefix="/hmc", tags=["HMC Moderation"])
PathId = Annotated[int, Path(gt=0, le=2_147_483_647)]


@router.get("/publication-requests", response_model=list[FeedReviewQueueItem],
            summary="List pending publication requests for HMC moderators/admins",
            description="Designated moderators see their groups' requests; admins also see unmapped requests. Full descriptions and reporter identity are internal-only.")
def read_publication_requests(response: Response,
    department_id: int | None = Query(None, gt=0, description="Optional department filter"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[FeedReviewQueueItem]:
    items, total = list_hmc_publication_review_queue(db, current_user,
        department_id=department_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/publication-requests/{complaint_id}/decision", response_model=FeedReviewResult,
             summary="Approve or reject a publication request for the responsible HMC group")
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


@router.get("/complaints/{complaint_id}/audiences", response_model=list[AudienceItem],
            summary="List HMC groups a complaint is published to")
def read_audiences(complaint_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[AudienceItem]:
    return list_complaint_audiences(db, current_user, complaint_id)


@router.post("/complaints/{complaint_id}/audiences", response_model=list[AudienceItem],
             summary="Share a published complaint with another HMC group on the same floor level",
             description="An explicit, audited shared-floor decision. Requires an admin or a moderator of both the responsible and the target group.")
def post_audience(payload: AudienceGrantRequest, complaint_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[AudienceItem]:
    return grant_shared_floor_audience(db, current_user, complaint_id, payload.hmc_group_id, payload.note)


@router.post("/complaints/{complaint_id}/audiences/{group_id}/revoke", response_model=list[AudienceItem],
             summary="Withdraw a shared-floor audience")
def post_audience_revoke(payload: AudienceRevokeRequest, complaint_id: PathId, group_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[AudienceItem]:
    return revoke_shared_floor_audience(db, current_user, complaint_id, group_id, payload.note)


@router.get("/groups", response_model=list[HMCGroupSummary],
            summary="List HMC groups and their canonical floors (moderators/admins)")
def read_groups(db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated)) -> list[HMCGroupSummary]:
    return list_hmc_groups(db, current_user)


@router.patch("/groups/{group_id}/moderators/{user_id}", response_model=ModerationActionResult,
              summary="Designate or remove an HMC group moderator (admin only)")
def patch_group_moderator(payload: ModeratorAssignmentRequest, group_id: PathId, user_id: PathId,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> ModerationActionResult:
    assign_hmc_moderator(db, current_user, group_id, user_id, assigned=payload.assigned)
    return ModerationActionResult(user_id=user_id, hmc_group_id=group_id,
        message="HMC moderator assignment updated.")
