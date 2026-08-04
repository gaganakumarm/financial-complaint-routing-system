"""Unit tests for the transaction-neutral authentication service."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models import User
from app.security import create_access_token, decode_access_token, hash_password
from app.services import (
    AuthenticationResult,
    AuthService,
    DuplicateEmailError,
    InactiveUserError,
    InvalidCredentialsError,
    UserNotFoundError,
    create_access_token_for_user,
)


PASSWORD = "valid-password"


def _repository() -> MagicMock:
    repository = MagicMock()
    for method in (
        "email_exists",
        "get_by_email",
        "get_by_id",
        "add",
        "flush",
        "refresh",
        "commit",
        "rollback",
        "begin",
    ):
        setattr(repository, method, AsyncMock())
    return repository


def _user(*, active: bool = True, user_id: UUID | None = None) -> User:
    return User(
        id=user_id if user_id is not None else uuid4(),
        role_id=uuid4(),
        email="person@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Example User",
        is_active=active,
        email_verified=False,
    )


@pytest.mark.anyio
async def test_successful_registration_normalizes_and_persists_user() -> None:
    repository = _repository()
    repository.email_exists.return_value = False
    repository.refresh.side_effect = lambda user: user
    role_id = uuid4()

    user = await AuthService(repository).register_user(
        email="  Person@Example.COM  ",
        password="  valid-password  ",
        full_name="  Example  User  ",
        role_id=role_id,
    )

    repository.email_exists.assert_awaited_once_with("person@example.com")
    repository.add.assert_awaited_once_with(user)
    repository.flush.assert_awaited_once_with()
    repository.refresh.assert_awaited_once_with(user)
    assert user.email == "person@example.com"
    assert user.full_name == "Example  User"
    assert user.password_hash != PASSWORD
    assert "valid-password" not in user.password_hash
    assert user.role_id == role_id
    assert user.is_active is True
    assert user.email_verified is False
    repository.commit.assert_not_awaited()
    repository.rollback.assert_not_awaited()
    repository.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_registration_returns_repository_refreshed_user() -> None:
    repository = _repository()
    refreshed_user = _user()
    repository.email_exists.return_value = False
    repository.refresh.return_value = refreshed_user

    result = await AuthService(repository).register_user(
        email="person@example.com",
        password=PASSWORD,
        full_name="Example User",
        role_id=uuid4(),
    )

    assert result is refreshed_user


@pytest.mark.anyio
async def test_duplicate_email_does_not_hash_or_mutate() -> None:
    repository = _repository()
    repository.email_exists.return_value = True

    with patch("app.services.auth.hash_password") as password_hasher:
        with pytest.raises(DuplicateEmailError):
            await AuthService(repository).register_user(
                email=" Person@Example.COM ",
                password=PASSWORD,
                full_name="Example User",
                role_id=uuid4(),
            )

    repository.email_exists.assert_awaited_once_with("person@example.com")
    password_hasher.assert_not_called()
    repository.add.assert_not_awaited()
    repository.flush.assert_not_awaited()
    repository.refresh.assert_not_awaited()


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        "person",
        "@example.com",
        "person@",
        "person@example",
        "person @example.com",
        "person@example .com",
        "person@@example.com",
        f"{'a' * 309}@example.com",
    ],
)
@pytest.mark.anyio
async def test_registration_rejects_invalid_email(email: str) -> None:
    repository = _repository()

    with pytest.raises(ValueError):
        await AuthService(repository).register_user(
            email=email,
            password=PASSWORD,
            full_name="Example User",
            role_id=uuid4(),
        )

    repository.email_exists.assert_not_awaited()


@pytest.mark.parametrize("full_name", ["", "   ", "a" * 201])
@pytest.mark.anyio
async def test_registration_rejects_invalid_full_name(full_name: str) -> None:
    repository = _repository()

    with pytest.raises(ValueError):
        await AuthService(repository).register_user(
            email="person@example.com",
            password=PASSWORD,
            full_name=full_name,
            role_id=uuid4(),
        )


@pytest.mark.parametrize("password", ["short", "x" * 129])
@pytest.mark.anyio
async def test_registration_rejects_invalid_password_length(password: str) -> None:
    repository = _repository()

    with pytest.raises(ValueError):
        await AuthService(repository).register_user(
            email="person@example.com",
            password=password,
            full_name="Example User",
            role_id=uuid4(),
        )


@pytest.mark.anyio
async def test_successful_authentication_normalizes_email() -> None:
    repository = _repository()
    user = _user()
    repository.get_by_email.return_value = user

    result = await AuthService(repository).authenticate(
        email=" Person@Example.COM ", password=PASSWORD
    )

    assert result is user
    repository.get_by_email.assert_awaited_once_with("person@example.com")
    repository.commit.assert_not_awaited()
    repository.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_wrong_password_raises_generic_credentials_error() -> None:
    repository = _repository()
    repository.get_by_email.return_value = _user()

    with pytest.raises(InvalidCredentialsError) as error:
        await AuthService(repository).authenticate(
            email="person@example.com", password="wrong-password"
        )

    assert str(error.value) == "Invalid credentials."


@pytest.mark.anyio
async def test_unknown_user_verifies_fixed_dummy_hash_once() -> None:
    repository = _repository()
    repository.get_by_email.return_value = None

    with patch("app.services.auth.verify_password", return_value=False) as verifier:
        with pytest.raises(InvalidCredentialsError) as error:
            await AuthService(repository).authenticate(
                email="unknown@example.com", password=PASSWORD
            )

    verifier.assert_called_once()
    assert verifier.call_args.args[0] == PASSWORD
    assert verifier.call_args.args[1].startswith("$argon2")
    assert str(error.value) == "Invalid credentials."


@pytest.mark.parametrize(
    ("password", "exception_type"),
    [(PASSWORD, InactiveUserError), ("wrong-password", InvalidCredentialsError)],
)
@pytest.mark.anyio
async def test_inactive_user_is_revealed_only_after_valid_password(
    password: str, exception_type: type[Exception]
) -> None:
    repository = _repository()
    repository.get_by_email.return_value = _user(active=False)

    with pytest.raises(exception_type):
        await AuthService(repository).authenticate(
            email="person@example.com", password=password
        )


def test_access_token_helper_uses_only_user_id_claims() -> None:
    user = _user()

    payload = decode_access_token(create_access_token_for_user(user))

    assert payload["sub"] == str(user.id)
    assert set(payload) == {"sub", "iat", "exp", "type"}


def test_access_token_helper_rejects_inactive_user() -> None:
    with pytest.raises(InactiveUserError):
        create_access_token_for_user(_user(active=False))


def test_access_token_helper_rejects_missing_user_id() -> None:
    user = User(
        role_id=uuid4(),
        email="person@example.com",
        password_hash="not-used",
        full_name="Example User",
        is_active=True,
        email_verified=False,
    )
    with pytest.raises(ValueError):
        create_access_token_for_user(user)


@pytest.mark.anyio
async def test_login_returns_immutable_authentication_result() -> None:
    repository = _repository()
    user = _user()
    repository.get_by_email.return_value = user

    result = await AuthService(repository).login(
        email="person@example.com", password=PASSWORD
    )

    assert isinstance(result, AuthenticationResult)
    assert result.user is user
    assert result.token_type == "bearer"
    assert decode_access_token(result.access_token)["sub"] == str(user.id)
    with pytest.raises(FrozenInstanceError):
        result.token_type = "other"  # type: ignore[misc]


@pytest.mark.anyio
async def test_failed_login_does_not_create_token() -> None:
    repository = _repository()
    repository.get_by_email.return_value = None

    with patch("app.services.auth.create_access_token_for_user") as token_creator:
        with pytest.raises(InvalidCredentialsError):
            await AuthService(repository).login(
                email="unknown@example.com", password=PASSWORD
            )

    token_creator.assert_not_called()


@pytest.mark.anyio
async def test_current_user_is_loaded_by_uuid_from_repository() -> None:
    repository = _repository()
    user = _user()
    repository.get_by_id.return_value = user

    result = await AuthService(repository).get_current_user(
        create_access_token(str(user.id))
    )

    assert result is user
    repository.get_by_id.assert_awaited_once_with(user.id)
    assert isinstance(repository.get_by_id.await_args.args[0], UUID)
    for method in ("commit", "rollback", "begin", "flush", "refresh"):
        getattr(repository, method).assert_not_awaited()


@pytest.mark.parametrize("token", ["malformed-token", "   "])
@pytest.mark.anyio
async def test_invalid_token_becomes_generic_credentials_error(token: str) -> None:
    repository = _repository()

    with pytest.raises(InvalidCredentialsError):
        await AuthService(repository).get_current_user(token)

    repository.get_by_id.assert_not_awaited()


@pytest.mark.anyio
async def test_expired_token_becomes_generic_credentials_error() -> None:
    repository = _repository()
    token = create_access_token(
        str(uuid4()),
        expires_delta=timedelta(minutes=1),
        now=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    with pytest.raises(InvalidCredentialsError):
        await AuthService(repository).get_current_user(token)


@pytest.mark.anyio
async def test_non_uuid_subject_becomes_generic_credentials_error() -> None:
    repository = _repository()

    with pytest.raises(InvalidCredentialsError):
        await AuthService(repository).get_current_user(
            create_access_token("not-a-uuid")
        )


@pytest.mark.anyio
async def test_missing_current_user_raises_user_not_found() -> None:
    repository = _repository()
    repository.get_by_id.return_value = None

    with pytest.raises(UserNotFoundError):
        await AuthService(repository).get_current_user(create_access_token(str(uuid4())))


@pytest.mark.anyio
async def test_inactive_current_user_is_rejected() -> None:
    repository = _repository()
    user = _user(active=False)
    repository.get_by_id.return_value = user

    with pytest.raises(InactiveUserError):
        await AuthService(repository).get_current_user(
            create_access_token(str(user.id))
        )


@pytest.mark.anyio
async def test_authentication_never_creates_a_token() -> None:
    repository = _repository()
    repository.get_by_email.return_value = _user()

    with patch("app.services.auth.create_access_token") as token_creator:
        await AuthService(repository).authenticate(
            email="person@example.com", password=PASSWORD
        )

    token_creator.assert_not_called()


@pytest.mark.anyio
async def test_exception_and_log_output_do_not_disclose_password(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    repository = _repository()
    repository.get_by_email.return_value = None
    supplied_password = "never-print-this-password"

    with pytest.raises(InvalidCredentialsError) as error:
        await AuthService(repository).authenticate(
            email="unknown@example.com", password=supplied_password
        )

    captured = capsys.readouterr()
    assert supplied_password not in str(error.value)
    assert supplied_password not in captured.out
    assert supplied_password not in captured.err
    assert supplied_password not in caplog.text


def test_importing_services_has_no_engine_or_service_side_effects() -> None:
    engine_loaded_before = "app.db.engine" in sys.modules

    import app.services as services

    importlib.reload(services)
    assert ("app.db.engine" in sys.modules) is engine_loaded_before
    assert not any(isinstance(value, AuthService) for value in vars(services).values())
