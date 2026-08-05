"""FastAPI dependency wiring for authenticated users."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session, get_transactional_session
from app.models import User
from app.repositories import (
    ComplaintRepository,
    ModelVersionRepository,
    PredictionRepository,
    ReviewRepository,
    UserRepository,
)
from app.prediction import ComplaintPredictor, ConfiguredBaselinePredictor
from app.services import (
    AuthService,
    ComplaintService,
    InactiveUserError,
    InvalidCredentialsError,
    PredictionService,
    ReviewService,
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


async def get_review_repository(session: DatabaseSession) -> ReviewRepository:
    return ReviewRepository(session)


async def get_transactional_review_repository(
    session: TransactionalDatabaseSession,
) -> ReviewRepository:
    return ReviewRepository(session)


async def get_prediction_repository(
    session: DatabaseSession,
) -> PredictionRepository:
    return PredictionRepository(session)


async def get_transactional_prediction_repository(
    session: TransactionalDatabaseSession,
) -> PredictionRepository:
    return PredictionRepository(session)


async def get_model_version_repository(
    session: DatabaseSession,
) -> ModelVersionRepository:
    return ModelVersionRepository(session)


async def get_transactional_model_version_repository(
    session: TransactionalDatabaseSession,
) -> ModelVersionRepository:
    return ModelVersionRepository(session)


ComplaintRepositoryDependency = Annotated[
    ComplaintRepository,
    Depends(get_complaint_repository),
]
TransactionalComplaintRepositoryDependency = Annotated[
    ComplaintRepository,
    Depends(get_transactional_complaint_repository),
]
ReviewRepositoryDependency = Annotated[ReviewRepository, Depends(get_review_repository)]
TransactionalReviewRepositoryDependency = Annotated[
    ReviewRepository, Depends(get_transactional_review_repository)
]
PredictionRepositoryDependency = Annotated[
    PredictionRepository, Depends(get_prediction_repository)
]
TransactionalPredictionRepositoryDependency = Annotated[
    PredictionRepository, Depends(get_transactional_prediction_repository)
]
ModelVersionRepositoryDependency = Annotated[
    ModelVersionRepository, Depends(get_model_version_repository)
]
TransactionalModelVersionRepositoryDependency = Annotated[
    ModelVersionRepository, Depends(get_transactional_model_version_repository)
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


def get_complaint_predictor() -> ComplaintPredictor:
    return ConfiguredBaselinePredictor()


ComplaintPredictorDependency = Annotated[
    ComplaintPredictor, Depends(get_complaint_predictor)
]


def get_prediction_service(
    complaint_repository: ComplaintRepositoryDependency,
    model_version_repository: ModelVersionRepositoryDependency,
    prediction_repository: PredictionRepositoryDependency,
    complaint_service: "ComplaintServiceDependency",
    predictor: ComplaintPredictorDependency,
) -> PredictionService:
    return PredictionService(
        complaint_repository=complaint_repository,
        model_version_repository=model_version_repository,
        prediction_repository=prediction_repository,
        complaint_service=complaint_service,
        predictor=predictor,
    )


def get_transactional_prediction_service(
    complaint_repository: TransactionalComplaintRepositoryDependency,
    model_version_repository: TransactionalModelVersionRepositoryDependency,
    prediction_repository: TransactionalPredictionRepositoryDependency,
    complaint_service: "TransactionalComplaintServiceDependency",
    predictor: ComplaintPredictorDependency,
) -> PredictionService:
    return PredictionService(
        complaint_repository=complaint_repository,
        model_version_repository=model_version_repository,
        prediction_repository=prediction_repository,
        complaint_service=complaint_service,
        predictor=predictor,
    )


def get_review_service(
    review_repository: ReviewRepositoryDependency,
    prediction_repository: PredictionRepositoryDependency,
    complaint_repository: ComplaintRepositoryDependency,
    complaint_service: "ComplaintServiceDependency",
) -> ReviewService:
    return ReviewService(
        review_repository=review_repository,
        prediction_repository=prediction_repository,
        complaint_repository=complaint_repository,
        complaint_service=complaint_service,
    )


def get_transactional_review_service(
    review_repository: TransactionalReviewRepositoryDependency,
    prediction_repository: TransactionalPredictionRepositoryDependency,
    complaint_repository: TransactionalComplaintRepositoryDependency,
    complaint_service: "TransactionalComplaintServiceDependency",
) -> ReviewService:
    return ReviewService(
        review_repository=review_repository,
        prediction_repository=prediction_repository,
        complaint_repository=complaint_repository,
        complaint_service=complaint_service,
    )


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
PredictionServiceDependency = Annotated[
    PredictionService, Depends(get_prediction_service)
]
TransactionalPredictionServiceDependency = Annotated[
    PredictionService, Depends(get_transactional_prediction_service)
]
ReviewServiceDependency = Annotated[ReviewService, Depends(get_review_service)]
TransactionalReviewServiceDependency = Annotated[
    ReviewService, Depends(get_transactional_review_service)
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
