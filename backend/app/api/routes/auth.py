"""Authentication API routes."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AuthServiceDependency, CurrentActiveUser
from app.schemas import (
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
    UserResponse,
)
from app.services import (
    DuplicateEmailError,
    InactiveUserError,
    InvalidCredentialsError,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
async def register_user(
    payload: RegisterRequest,
    auth_service: AuthServiceDependency,
) -> RegistrationResponse:
    try:
        user = await auth_service.register_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role_id=payload.role_id,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid registration data",
        ) from None

    return RegistrationResponse(user=UserResponse.model_validate(user))


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
async def login(
    payload: LoginRequest,
    auth_service: AuthServiceDependency,
) -> TokenResponse:
    try:
        result = await auth_service.login(
            email=payload.email,
            password=payload.password,
        )
    except (InvalidCredentialsError, InactiveUserError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return TokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
    )


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentActiveUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
