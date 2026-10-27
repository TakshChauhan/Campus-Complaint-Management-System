from app.models.student_residence import StudentResidence
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.hostel import Hostel
from datetime import date
from typing import List, Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_student
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintListItem,
    ComplaintResponse,
    ComplaintReopenRequest,
    ComplaintReopenResponse,
)
from app.schemas.complaint_history import ComplaintStatusHistoryItem
from app.schemas.department import (
    DepartmentSuggestionRequest,
    DepartmentSuggestionResponse,
)
from app.schemas.duplicate import (
    DuplicateSuggestionRequest,
    DuplicateSuggestionsResponse,
)
from app.services.complaint_service import (
    create_student_complaint,
    get_my_complaint,
    get_my_complaints,
    reopen_student_complaint,
)
from app.services.duplicate_service import (
    DEFAULT_THRESHOLD,
    find_similar,
)
from app.services.suggestion_service import SuggestionService

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post(
    "/suggest",
    response_model=DepartmentSuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "[Sprint 1 Contract] Advisory department suggestion "
        "based on complaint draft"
    ),
    description=(
        "Advisory department recommendations based on complaint "
        "title and description. The student retains the final choice."
    ),
    responses={
        200: {"description": "Advisory department recommendations"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Only students can request suggestions"},
    },
)
def suggest_complaint_department(
    payload: DepartmentSuggestionRequest,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> DepartmentSuggestionResponse:
    service = SuggestionService(db)

    return service.suggest_departments(
        title=payload.title,
        description=payload.description,
    )


@router.post(
    "/duplicate-suggestions",
    response_model=DuplicateSuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Suggest similar accessible complaints",
)
def get_duplicate_suggestions(
    payload: DuplicateSuggestionRequest,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> DuplicateSuggestionsResponse:
    try:
        # Find the student's verified and active residence.
        residence = (
            db.query(StudentResidence)
            .join(
                HostelFloor,
                StudentResidence.floor_id == HostelFloor.id,
            )
            .join(
                HostelWing,
                HostelFloor.wing_id == HostelWing.id,
            )
            .join(
                Hostel,
                HostelWing.hostel_id == Hostel.id,
            )
            .filter(
                StudentResidence.student_id == current_student.id,
                StudentResidence.status == "verified",
                StudentResidence.verified_at.isnot(None),
                HostelFloor.is_active.is_(True),
                HostelWing.is_active.is_(True),
                Hostel.is_active.is_(True),
            )
            .first()
        )

        # Without verified residence, return no suggestions.
        if residence is None:
            candidates = []
        else:
            # Same-floor public complaints and the student's own
            # private complaints are eligible candidates.
            candidates = (
                db.query(Complaint)
                .filter(
                    Complaint.floor_id == residence.floor_id,
                    or_(
                        Complaint.is_public.is_(True),
                        Complaint.created_by_id == current_student.id,
                    ),
                )
                .all()
            )

        matches = find_similar(
            title=payload.title,
            description=payload.description,
            candidates=candidates,
            threshold=DEFAULT_THRESHOLD,
            top_k=3,
        )

    except Exception:
        import logging

        logging.getLogger("ccms.backend").exception(
            "Duplicate suggestions failed; returning empty results"
        )
        matches = []

    return DuplicateSuggestionsResponse(
        matches=matches,
        threshold=DEFAULT_THRESHOLD,
        disclaimer=(
            "Similarity scores are advisory only. "
            "You can submit your complaint even when matches exist."
        ),
    )


@router.post(
    "",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new complaint",
    description=(
        "Allows an authenticated student to file a campus grievance "
        "against an active department."
    ),
    responses={
        201: {"description": "Complaint successfully submitted and persisted"},
        400: {
            "description": (
                "Validation failure or target department is inactive"
            )
        },
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Only students can file complaints"},
        404: {"description": "Target department not found"},
    },
)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> ComplaintResponse:
    return create_student_complaint(
        db=db,
        complaint_in=payload,
        student=current_student,
    )


@router.get(
    "/mine",
    response_model=List[ComplaintListItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve personal complaint history",
    description=(
        "Returns complaints registered by the authenticated student "
        "with limit/offset pagination and optional filters."
    ),
    responses={
        200: {"description": "Personal complaint history list"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Only students can access personal history"},
        422: {"description": "Invalid query parameter"},
    },
)
def read_my_complaints(
    response: Response,
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum number of complaints to return",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Offset for pagination",
    ),
    q: Optional[str] = Query(
        None,
        max_length=120,
        description="Search by reference, title or description",
    ),
    department_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter by department ID",
    ),
    date_from: Optional[date] = Query(
        None,
        description="Only complaints submitted on/after this date (UTC)",
    ),
    date_to: Optional[date] = Query(
        None,
        description="Only complaints submitted on/before this date (UTC)",
    ),
    sort: Literal["newest", "oldest"] = Query(
        "newest",
        description="Sort order by submission time",
    ),
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> List[ComplaintListItem]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must be on or before date_to.",
        )

    items, total = get_my_complaints(
        db=db,
        student_id=current_student.id,
        limit=limit,
        offset=offset,
        q=q,
        department_id=department_id,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
    )

    response.headers["X-Total-Count"] = str(total)
    return items


@router.get(
    "/{complaint_id}/history",
    response_model=List[ComplaintStatusHistoryItem],
)
def read_complaint_status_history(
    complaint_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    complaint = (
        db.query(Complaint)
        .filter(Complaint.id == complaint_id)
        .first()
    )

    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    if current_user.role == "student":
        allowed = complaint.created_by_id == current_user.id

    elif current_user.role == "staff":
        allowed = (
            getattr(current_user, "department_id", None) is not None
            and complaint.department_id == current_user.department_id
        )

    elif current_user.role == "admin":
        allowed = True

    else:
        allowed = False

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    return (
        db.query(ComplaintStatusHistory)
        .filter(ComplaintStatusHistory.complaint_id == complaint_id)
        .order_by(
            ComplaintStatusHistory.created_at.asc(),
            ComplaintStatusHistory.id.asc(),
        )
        .all()
    )


@router.post(
    "/{complaint_id}/reopen",
    response_model=ComplaintReopenResponse,
)
def reopen_complaint(
    complaint_id: int = Path(..., gt=0),
    payload: Optional[ComplaintReopenRequest] = None,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
):
    complaint = reopen_student_complaint(
        db=db,
        student=current_student,
        complaint_id=complaint_id,
        remark=payload.remark if payload else None,
    )

    return ComplaintReopenResponse(
        id=complaint.id,
        status=complaint.status,
        reopen_count=complaint.reopen_count,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
)
def read_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
):
    return get_my_complaint(
        db=db,
        student_id=current_student.id,
        complaint_id=complaint_id,
    )
