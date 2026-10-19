from datetime import date
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_student
from app.models.user import User
from app.schemas.complaint import ComplaintCreate, ComplaintListItem, ComplaintResponse
from app.schemas.department import (
    DepartmentSuggestionRequest,
    DepartmentSuggestionResponse,
)
from app.services.complaint_service import (
    create_student_complaint,
    get_my_complaint,
    get_my_complaints,
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
