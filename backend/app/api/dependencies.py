"""FastAPI dependency wiring for authenticated users."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session, get_transactional_session
from app.models import User
from app.repositories import ComplaintRepository, UserRepository
from app.services import (
    AuthService,
    ComplaintService,
    InactiveUserError,
    InvalidCredentialsError,
    UserNotFoundError,
)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
TransactionalDatabaseSession = Annotated[
    AsyncSession,
    Depends(get_transactional_session),
]


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRepository:
    """Construct a user repository around the injected session."""
    return UserRepository(session)


async def get_transactional_user_repository(
    session: Annotated[AsyncSession, Depends(get_transactional_session)],
) -> UserRepository:
    """Construct a user repository around the request transaction session."""
    return UserRepository(session)


async def get_complaint_repository(
    session: DatabaseSession,
) -> ComplaintRepository:
    """Construct a complaint repository around a read-only session."""
    return ComplaintRepository(session)


async def get_transactional_complaint_repository(
    session: TransactionalDatabaseSession,
) -> ComplaintRepository:
    """Construct a complaint repository around the request transaction."""
    return ComplaintRepository(session)


ComplaintRepositoryDependency = Annotated[
    ComplaintRepository,
    Depends(get_complaint_repository),
]
TransactionalComplaintRepositoryDependency = Annotated[
    ComplaintRepository,
    Depends(get_transactional_complaint_repository),
]


def get_complaint_service(
    complaint_repository: ComplaintRepositoryDependency,
) -> ComplaintService:
    """Construct a read-only complaint service."""
    return ComplaintService(complaint_repository)


def get_transactional_complaint_service(
    complaint_repository: TransactionalComplaintRepositoryDependency,
) -> ComplaintService:
    """Construct a complaint service inside the request transaction."""
    return ComplaintService(complaint_repository)


def get_auth_service(
    user_repository: Annotated[
        UserRepository,
        Depends(get_user_repository),
    ],
) -> AuthService:
    """Construct an authentication service around the injected repository."""
    return AuthService(user_repository)


def get_transactional_auth_service(
    user_repository: Annotated[
        UserRepository,
        Depends(get_transactional_user_repository),
    ],
) -> AuthService:
    """Construct an authentication service inside the request transaction."""
    return AuthService(user_repository)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """Resolve a bearer token to its current persisted user."""
    try:
        return await auth_service.get_current_user(token)
    except (InvalidCredentialsError, InactiveUserError, UserNotFoundError):
        raise _credentials_exception() from None


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Return the service-validated active user unchanged."""
    return current_user


ComplaintServiceDependency = Annotated[
    ComplaintService,
    Depends(get_complaint_service),
]
TransactionalComplaintServiceDependency = Annotated[
    ComplaintService,
    Depends(get_transactional_complaint_service),
]
UserRepositoryDependency = Annotated[
    UserRepository,
    Depends(get_user_repository),
]
AuthServiceDependency = Annotated[
    AuthService,
    Depends(get_auth_service),
]
TransactionalUserRepositoryDependency = Annotated[
    UserRepository,
    Depends(get_transactional_user_repository),
]
TransactionalAuthServiceDependency = Annotated[
    AuthService,
    Depends(get_transactional_auth_service),
]
AccessToken = Annotated[str, Depends(oauth2_scheme)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
