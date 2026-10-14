from fastapi import APIRouter, Depends, status

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserSafeResponse

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
