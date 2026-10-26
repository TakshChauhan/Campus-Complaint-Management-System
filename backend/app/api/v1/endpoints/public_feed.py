"""Privacy-safe student feeds and designated HMC moderation endpoints."""
from typing import Literal
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated, require_student
from app.models.user import User
from app.schemas.public_feed import (
    FeedComplaintDetail, FeedComplaintItem, FeedLocationCatalogue, FeedReviewQueueItem,
    FeedReviewRequest, FeedReviewResult, ModerationActionResult, ModeratorAssignmentRequest,
    ResidenceVerificationRequest, UnpublishRequest,
)
from app.services.public_feed_service import (
    assign_hmc_moderator, get_accessible_feed_complaint_detail, list_department_public_feed,
    list_feed_locations, list_hmc_publication_review_queue, list_student_hmc_feed,
    review_hmc_publication, unpublish_hmc_complaint, verify_student_residence,
)

router = APIRouter(prefix="/complaints/feed", tags=["Public Complaint Feed"])
StatusFilter = Literal["submitted", "in_progress", "resolved", "reopened"]


@router.get("/locations", response_model=FeedLocationCatalogue,
            summary="List configured building, floor and wing choices")
def read_feed_location_catalogue(db: Session = Depends(get_db),
                                 current_student: User = Depends(require_student)) -> FeedLocationCatalogue:
    return list_feed_locations(db)


@router.get("", response_model=list[FeedComplaintItem],
            summary="Browse published complaints for one department",
            description="Returns only published department-wide summaries. No complaint description, reporter identity or moderation details are returned.")
def read_department_public_feed(response: Response,
    department_id: int = Query(..., gt=0),
    status_filter: StatusFilter | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_student: User = Depends(require_student)) -> list[FeedComplaintItem]:
    items, total = list_department_public_feed(db, department_id=department_id,
        status_filter=status_filter, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/hmc", response_model=list[FeedComplaintItem],
            summary="Browse the authenticated student's verified-residence HMC feed",
            description="Membership is derived from the staff-verified building, floor and wing assignment. Student feed responses never include complaint descriptions or reporter identity.")
def read_student_hmc_feed(response: Response,
    status_filter: StatusFilter | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_student: User = Depends(require_student)) -> list[FeedComplaintItem]:
    items, total = list_student_hmc_feed(db, current_student,
        status_filter=status_filter, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/items/{complaint_id}", response_model=FeedComplaintDetail,
            summary="View privacy-safe metadata for a complaint visible in the student's feed",
            description="This endpoint repeats the feed access check and intentionally does not return the full complaint description.")
def read_accessible_feed_complaint_detail(
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db), current_student: User = Depends(require_student)) -> FeedComplaintDetail:
    return get_accessible_feed_complaint_detail(db, current_student, complaint_id)


@router.get("/review-queue", response_model=list[FeedReviewQueueItem],
            summary="List pending publication requests for HMC moderators/admins",
            description="Only designated HMC moderators for the affected location and administrators can access this queue. Full descriptions and reporter identity are internal-only.")
def read_hmc_feed_review_queue(response: Response,
    department_id: int | None = Query(None, gt=0, description="Optional department filter"),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> list[FeedReviewQueueItem]:
    items, total = list_hmc_publication_review_queue(db, current_user,
        department_id=department_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/review/{complaint_id}", response_model=FeedReviewResult,
             summary="Approve or reject a publication request")
def review_hmc_feed_publication(payload: FeedReviewRequest,
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> FeedReviewResult:
    return review_hmc_publication(db, current_user, complaint_id, payload)


@router.post("/unpublish/{complaint_id}", response_model=ModerationActionResult,
             summary="Remove a currently published complaint from student feeds")
def unpublish_feed_complaint(payload: UnpublishRequest,
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> ModerationActionResult:
    complaint = unpublish_hmc_complaint(db, current_user, complaint_id, payload.note)
    return ModerationActionResult(complaint_id=complaint.id,
        publication_status=complaint.publication_status,
        message="Complaint unpublished. The moderation action was recorded in the audit trail.")


@router.post("/residence/{student_id}/verify", response_model=ModerationActionResult,
             summary="Record an administrator-verified student residence")
def verify_residence(payload: ResidenceVerificationRequest,
    student_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> ModerationActionResult:
    student = verify_student_residence(db, current_user, student_id,
        building_id=payload.building_id, floor_id=payload.floor_id, wing_id=payload.wing_id)
    return ModerationActionResult(user_id=student.id,
        message="Residence assignment was recorded as verified by an administrator.")


@router.put("/hmc-groups/{group_id}/moderators/{user_id}", response_model=ModerationActionResult,
            summary="Designate or remove an HMC group moderator")
def set_hmc_moderator(payload: ModeratorAssignmentRequest,
    group_id: int = Path(..., gt=0), user_id: int = Path(..., gt=0),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_authenticated)) -> ModerationActionResult:
    assign_hmc_moderator(db, current_user, group_id, user_id, assigned=payload.assigned)
    return ModerationActionResult(user_id=user_id, hmc_group_id=group_id,
        message="HMC moderator assignment updated.")
