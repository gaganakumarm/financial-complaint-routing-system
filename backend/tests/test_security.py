"""Unit tests for security configuration, passwords, and access tokens."""

from datetime import datetime, timedelta, timezone
import importlib
import sys

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.security import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


TEST_SECRET = "test-only-secret-key-with-at-least-32-characters"


@pytest.fixture(autouse=True)
def security_settings(monkeypatch: pytest.MonkeyPatch):
    """Use deterministic, valid security settings in every test."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_security_configuration_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 30
    assert len(settings.jwt_secret_key) >= 32


def test_security_configuration_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", f"  {TEST_SECRET}  ")
    monkeypatch.setenv("JWT_ALGORITHM", " HS256 ")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key == TEST_SECRET
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 45


@pytest.mark.parametrize("secret", ["", "   ", "too-short"])
def test_invalid_jwt_secrets_are_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key=secret, _env_file=None)


@pytest.mark.parametrize("algorithm", ["none", "RS256", "", "   "])
def test_unsupported_jwt_algorithms_are_rejected(algorithm: str) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_algorithm=algorithm, _env_file=None)


@pytest.mark.parametrize("minutes", [0, 1441])
def test_access_token_expiry_bounds_are_enforced(minutes: int) -> None:
    with pytest.raises(ValidationError):
        Settings(access_token_expire_minutes=minutes, _env_file=None)


def test_password_hashing_and_verification() -> None:
    password = "correct horse battery staple"
    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != password
    assert first_hash.startswith("$argon2")
    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password("wrong password", first_hash) is False


def test_password_surrounding_whitespace_is_normalized() -> None:
    password_hash = hash_password("  secret123  ")

    assert verify_password("secret123", password_hash) is True
    assert verify_password("  secret123  ", password_hash) is True


def test_password_internal_whitespace_is_preserved() -> None:
    password_hash = hash_password("secret 123")

    assert verify_password("secret 123", password_hash) is True
    assert verify_password("secret  123", password_hash) is False


@pytest.mark.parametrize("password", ["", "   "])
def test_blank_password_is_rejected(password: str) -> None:
    with pytest.raises(ValueError):
        hash_password(password)
    with pytest.raises(ValueError):
        verify_password(password, "valid-looking-hash")


@pytest.mark.parametrize("password_hash", ["", "   "])
def test_blank_stored_hash_is_rejected(password_hash: str) -> None:
    with pytest.raises(ValueError):
        verify_password("password", password_hash)


def test_malformed_stored_hash_returns_false() -> None:
    assert verify_password("password", "not-a-supported-hash") is False


def test_password_material_is_not_printed_or_logged(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext = "do-not-disclose-this-password"
    password_hash = hash_password(plaintext)
    verify_password(plaintext, password_hash)

    captured = capsys.readouterr()
    assert plaintext not in captured.out
    assert plaintext not in captured.err
    assert plaintext not in caplog.text


def test_access_token_creation_and_default_expiry() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    token = create_access_token("  example-user  ", now=now)
    payload = decode_access_token(token)

    assert isinstance(token, str) and token
    assert payload["sub"] == "example-user"
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]
    assert payload["exp"] - payload["iat"] == 30 * 60


def test_access_token_custom_positive_expiry() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = decode_access_token(
        create_access_token("example-user", expires_delta=timedelta(minutes=5), now=now)
    )

    assert payload["exp"] - payload["iat"] == 5 * 60


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
def test_nonpositive_custom_expiry_is_rejected(delta: timedelta) -> None:
    with pytest.raises(ValueError):
        create_access_token("example-user", expires_delta=delta)


def test_blank_subject_is_rejected() -> None:
    with pytest.raises(ValueError):
        create_access_token("   ")


def _signed_payload(**overrides: object) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload: dict[str, object] = {
        "sub": "example-user",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "access",
    }
    payload.update(overrides)
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def test_wrong_signing_secret_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "user", "iat": now, "exp": now + timedelta(minutes=5), "type": "access"},
        "different-test-secret-key-with-at-least-32-characters",
        algorithm="HS256",
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not.a.valid-token")


def test_blank_token_is_rejected() -> None:
    with pytest.raises(ValueError):
        decode_access_token("   ")


def test_expired_token_raises_specific_exception() -> None:
    token = create_access_token(
        "example-user",
        expires_delta=timedelta(minutes=1),
        now=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    with pytest.raises(ExpiredAccessTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("missing_claim", ["sub", "iat", "exp", "type"])
def test_missing_required_claim_is_rejected(missing_claim: str) -> None:
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "sub": "example-user",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "access",
    }
    del payload[missing_claim]
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("overrides", [{"sub": "   "}, {"type": "refresh"}])
def test_invalid_subject_or_token_type_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(_signed_payload(**overrides))


def test_unsupported_algorithm_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "user", "iat": now, "exp": now + timedelta(minutes=5), "type": "access"},
        TEST_SECRET,
        algorithm="HS384",
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_modified_token_is_rejected() -> None:
    token = _signed_payload()
    header, payload, signature = token.split(".")
    index = len(payload) // 2
    replacement = "A" if payload[index] != "A" else "B"
    modified_payload = f"{payload[:index]}{replacement}{payload[index + 1:]}"

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(f"{header}.{modified_payload}.{signature}")


def test_security_package_import_has_no_database_side_effects() -> None:
    database_modules_before = {name for name in sys.modules if name.startswith("app.db")}

    import app.security as security

    importlib.reload(security)
    database_modules_after = {name for name in sys.modules if name.startswith("app.db")}
    assert database_modules_after == database_modules_before
