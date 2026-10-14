from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_student
from app.models.user import User
from app.schemas.department import (
    DepartmentResponse,
    DepartmentSuggestionItem,
    DepartmentSuggestionRequest,
    DepartmentSuggestionResponse,
)
from app.services.department_service import get_active_departments

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get(
    "",
    response_model=List[DepartmentResponse],
    status_code=status.HTTP_200_OK,
    summary="List active departments",
    description="Returns all active campus departments in deterministic alphabetical order. Requires an authenticated session so students can choose a target department for complaints.",
    responses={
        200: {"description": "Deterministic list of active departments"},
        401: {"description": "Missing or invalid bearer token"},
    },
)
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DepartmentResponse]:
    departments = get_active_departments(db)
    return [DepartmentResponse.model_validate(dept) for dept in departments]


@router.post(
    "/suggest",
    response_model=DepartmentSuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary="[Contract] Advisory keyword-based department suggestions",
    description="Agreed API contract for automated keyword-based advisory department suggestions. Evaluates complaint title/description drafts and returns ranked suggestions based on campus department heuristics. Note: Suggestions are purely advisory; the student always retains final authoritative choice.",
    responses={
        200: {"description": "Advisory department recommendations"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "Forbidden: Only students can request suggestions"},
    },
)
def suggest_department(
    payload: DepartmentSuggestionRequest,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> DepartmentSuggestionResponse:
    from app.services.suggestion_service import SuggestionService
    service = SuggestionService(db)
    return service.suggest_departments(title=payload.title, description=payload.description)
