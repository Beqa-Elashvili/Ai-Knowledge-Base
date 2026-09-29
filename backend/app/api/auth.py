"""Auth endpoints. Registration/login happen in the browser via Supabase Auth;
the backend only verifies access tokens."""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user
from app.schemas import ErrorResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse, responses={401: {"model": ErrorResponse}})
def me(user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)
