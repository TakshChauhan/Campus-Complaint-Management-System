from datetime import date
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_any_authenticated, require_student
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
from app.services.complaint_service import (
    create_student_complaint,
    get_my_complaint,
    get_my_complaints,
    reopen_student_complaint,
)
from app.services.suggestion_service import SuggestionService

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post(
    "/suggest",
    response_model=DepartmentSuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary="[Sprint 1 Contract] Advisory department suggestion based on complaint draft",
    description="Agreed API contract endpoint (POST /api/v1/complaints/suggest) evaluating complaint title and description to advise likely target department. Purely advisory; student retains final choice.",
    responses={
        200: {"description": "Advisory department recommendations"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: Only students can request suggestions"},
    },
)
def suggest_complaint_department(
    payload: DepartmentSuggestionRequest,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> DepartmentSuggestionResponse:
    service = SuggestionService(db)
    return service.suggest_departments(title=payload.title, description=payload.description)



@router.post(
    "",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new complaint",
    description="Allows an authenticated student to file a campus grievance against an active department. Generates an immutable server-side timestamp and initial status 'submitted'.",
    responses={
        201: {"description": "Complaint successfully submitted and persisted"},
        400: {"description": "Validation failure or target department is inactive"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: Only students can file complaints"},
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
        "Returns complaints registered by the authenticated student with limit/offset pagination. "
        "Optional server-side filters: `q` (matches complaint reference such as `CMP-12`, title or description), "
        "`department_id`, `date_from`/`date_to` (inclusive, YYYY-MM-DD, UTC) and `sort` (`newest` or `oldest`). "
        "Filters apply to the student's entire history before pagination. The `X-Total-Count` response header "
        "carries the total number of matching complaints. Students cannot view grievances filed by other users."
    ),
    responses={
        200: {"description": "Personal complaint history list (empty if none lodged)"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: Only students possess a personal complaint history"},
        422: {"description": "Invalid query parameter"},
    },
)
def read_my_complaints(
    response: Response,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of complaints to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    q: Optional[str] = Query(None, max_length=120, description="Search by reference (CMP-12), title or description"),
    department_id: Optional[int] = Query(None, gt=0, description="Filter by department ID"),
    date_from: Optional[date] = Query(None, description="Only complaints submitted on/after this date (UTC)"),
    date_to: Optional[date] = Query(None, description="Only complaints submitted on/before this date (UTC)"),
    sort: Literal["newest", "oldest"] = Query("newest", description="Sort order by submission time"),
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> List[ComplaintListItem]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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




@router.post(
    "/{complaint_id}/reopen",
    response_model=ComplaintReopenResponse,
    status_code=status.HTTP_200_OK,
    summary="Reopen one of the authenticated student's resolved complaints",
    description=(
        "Reopens a complaint submitted by the authenticated student. A complaint may be reopened "
        "at most twice and only within seven days of resolution. The reopen event is recorded in "
        "status history as part of the lifecycle service operation."
    ),
    responses={
        400: {"description": "Reopen limit reached, window expired, or resolution timestamp missing"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: only students can reopen complaints"},
        404: {"description": "Complaint not found or not owned by the caller"},
        409: {"description": "Complaint is not currently resolved"},
        422: {"description": "Invalid complaint ID or request body"},
    },
)
def reopen_complaint(
    payload: ComplaintReopenRequest | None = None,
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> ComplaintReopenResponse:
    """Delegate reopen eligibility and atomic status/history mutation to the lifecycle service."""
    reopened = reopen_student_complaint(
        db=db,
        student=current_student,
        complaint_id=complaint_id,
        remark=payload.remark if payload is not None else None,
    )
    return ComplaintReopenResponse.model_validate(reopened)


@router.get(
    "/{complaint_id}/history",
    response_model=List[ComplaintStatusHistoryItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve the status timeline for an accessible complaint",
    description=(
        "Returns complaint status events in chronological order. Students can access only their own "
        "complaints; staff can access complaints assigned to their department; administrators can access "
        "any existing complaint. Out-of-scope complaint IDs return 404."
    ),
    responses={
        401: {"description": "Missing or invalid bearer token"},
        404: {"description": "Complaint not found or not accessible to the caller"},
        422: {"description": "Invalid complaint ID"},
    },
)
def read_complaint_status_history(
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_authenticated),
) -> List[ComplaintStatusHistoryItem]:
    """Return an authorized complaint's history without exposing user profile details."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    # Enforce access on the server and hide out-of-scope complaint existence.
    if current_user.role == "student":
        allowed = complaint.created_by_id == current_user.id
    elif current_user.role == "staff":
        allowed = (
            current_user.department_id is not None
            and complaint.department_id == current_user.department_id
        )
    elif current_user.role == "admin":
        # Administrative history access is an assumption to confirm with the lead.
        allowed = True
    else:
        allowed = False

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        )

    events = (
        db.query(ComplaintStatusHistory)
        .filter(ComplaintStatusHistory.complaint_id == complaint.id)
        .order_by(
            ComplaintStatusHistory.created_at.asc(),
            ComplaintStatusHistory.id.asc(),
        )
        .all()
    )
    return events


@router.get(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve one of your own complaints",
    description="Returns full details of a complaint owned by the authenticated student. Complaints owned by other users return 404.",
    responses={
        200: {"description": "Complaint details"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: Only students can read their complaints"},
        404: {"description": "Complaint not found (or not owned by the caller)"},
    },
)
def read_my_complaint(
    complaint_id: int = Path(..., gt=0, le=2_147_483_647),
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> ComplaintResponse:
    return get_my_complaint(db=db, student_id=current_student.id, complaint_id=complaint_id)
