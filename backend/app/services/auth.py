"""Transaction-neutral authentication business logic."""

from dataclasses import dataclass
from uuid import UUID

from app.models import User
from app.repositories import UserRepository
from app.security import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class AuthenticationError(Exception):
    """Base exception for authentication service failures."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when supplied credentials cannot be authenticated."""


class InactiveUserError(AuthenticationError):
    """Raised when an authenticated user account is inactive."""


class DuplicateEmailError(AuthenticationError):
    """Raised when registration would duplicate an email address."""


class UserNotFoundError(AuthenticationError):
    """Raised when a token subject no longer identifies a user."""


_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials."
_INACTIVE_USER_MESSAGE = "User account is inactive."
_DUPLICATE_EMAIL_MESSAGE = "An account with this email already exists."
_USER_NOT_FOUND_MESSAGE = "User not found."
_DUMMY_PASSWORD_HASH = hash_password("fixed-dummy-password-used-only-for-timing")


def _normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("email must be a string")
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("email cannot be blank")
    if len(normalized) > 320:
        raise ValueError("email cannot exceed 320 characters")
    if any(character.isspace() for character in normalized):
        raise ValueError("email cannot contain whitespace")
    if normalized.count("@") != 1:
        raise ValueError("email must contain exactly one @")
    local_part, domain = normalized.split("@")
    if not local_part or not domain:
        raise ValueError("email must contain a local part and domain")
    if "." not in domain:
        raise ValueError("email domain must contain a dot")
    return normalized


def _normalize_full_name(full_name: str) -> str:
    if not isinstance(full_name, str):
        raise ValueError("full name must be a string")
    normalized = full_name.strip()
    if not normalized:
        raise ValueError("full name cannot be blank")
    if len(normalized) > 200:
        raise ValueError("full name cannot exceed 200 characters")
    return normalized


def _validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise ValueError("password must be a string")
    normalized = password.strip()
    if not normalized:
        raise ValueError("password cannot be blank")
    if len(normalized) < 8:
        raise ValueError("password must contain at least 8 characters")
    if len(normalized) > 128:
        raise ValueError("password cannot exceed 128 characters")
    return normalized


def create_access_token_for_user(user: User) -> str:
    """Issue an access token containing only the active user's identifier."""
    if not user.is_active:
        raise InactiveUserError(_INACTIVE_USER_MESSAGE)
    if user.id is None:
        raise ValueError("user ID must be populated")
    return create_access_token(str(user.id))


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """Successful login result."""

    user: User
    access_token: str
    token_type: str = "bearer"


class AuthService:
    """Coordinate user registration and authentication operations."""

    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        role_id: UUID,
    ) -> User:
        normalized_email = _normalize_email(email)
        normalized_full_name = _normalize_full_name(full_name)
        normalized_password = _validate_password(password)

        if await self._user_repository.email_exists(normalized_email):
            raise DuplicateEmailError(_DUPLICATE_EMAIL_MESSAGE)

        user = User(
            email=normalized_email,
            password_hash=hash_password(normalized_password),
            full_name=normalized_full_name,
            role_id=role_id,
            is_active=True,
            email_verified=False,
        )
        await self._user_repository.add(user)
        await self._user_repository.flush()
        return await self._user_repository.refresh(user)

    async def authenticate(self, *, email: str, password: str) -> User:
        normalized_email = _normalize_email(email)
        normalized_password = _validate_password(password)
        user = await self._user_repository.get_by_email(normalized_email)

        if user is None:
            verify_password(normalized_password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError(_INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(normalized_password, user.password_hash):
            raise InvalidCredentialsError(_INVALID_CREDENTIALS_MESSAGE)
        if not user.is_active:
            raise InactiveUserError(_INACTIVE_USER_MESSAGE)
        return user

    async def login(self, *, email: str, password: str) -> AuthenticationResult:
        user = await self.authenticate(email=email, password=password)
        return AuthenticationResult(
            user=user,
            access_token=create_access_token_for_user(user),
        )

    async def get_current_user(self, token: str) -> User:
        try:
            payload = decode_access_token(token)
        except (ExpiredAccessTokenError, InvalidAccessTokenError, ValueError):
            raise InvalidCredentialsError(_INVALID_CREDENTIALS_MESSAGE) from None

        try:
            user_id = UUID(str(payload["sub"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise InvalidCredentialsError(_INVALID_CREDENTIALS_MESSAGE) from None

        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(_USER_NOT_FOUND_MESSAGE)
        if not user.is_active:
            raise InactiveUserError(_INACTIVE_USER_MESSAGE)
        return user
