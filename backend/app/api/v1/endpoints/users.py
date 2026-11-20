from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_student
from app.models.user import User
from app.schemas.residence import MyResidence, ResidenceUpdate
from app.schemas.user import ChangePasswordRequest, ChangePasswordResponse, UserSafeResponse
from app.services.password_reset_service import change_current_user_password
from app.services.residence_service import get_my_residence, set_my_residence

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserSafeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Returns the authenticated user's profile details including assigned role and department ID. Never exposes sensitive password hashes.",
    responses={
        200: {"description": "Current user profile"},
        401: {"description": "Missing, expired, or invalid bearer token"},
        403: {"description": "User account is deactivated"},
    },
)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserSafeResponse:
    return UserSafeResponse.model_validate(current_user)


@router.get(
    "/me/residence",
    response_model=MyResidence,
    summary="Get the authenticated student's residence and verification state",
    responses={
        403: {"description": "Only students have a residence"},
        404: {"description": "No residence has been set"},
    },
)
def read_my_residence(
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> MyResidence:
    return get_my_residence(db, current_student)


@router.patch(
    "/me/residence",
    response_model=MyResidence,
    summary="Set or change the authenticated student's residence (returns to pending)",
    responses={
        403: {"description": "Only students have a residence"},
        422: {"description": "Unknown or inactive floor, or invalid body"},
    },
)
def update_my_residence(
    payload: ResidenceUpdate,
    db: Session = Depends(get_db),
    current_student: User = Depends(require_student),
) -> MyResidence:
    return set_my_residence(db, current_student, payload.floor_id)


@router.post(
    "/me/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password for authenticated user",
    description="Updates the authenticated user's account password after verifying their current password.",
    responses={
        200: {"description": "Password changed successfully"},
        400: {"description": "Incorrect current password, or new password is identical to current"},
        401: {"description": "Missing or invalid bearer token"},
        422: {"description": "Validation error on new password format"},
    },
)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChangePasswordResponse:
    change_current_user_password(
        db=db,
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return ChangePasswordResponse()
