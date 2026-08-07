"""Tests for typed application configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, Settings, get_settings


def test_default_values() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Financial Complaint Routing System API"
    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.debug is False
    assert settings.api_prefix == "/api"
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_environment_variable_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FCRS_APP_NAME", "Configured API")
    monkeypatch.setenv("FCRS_APP_ENV", "testing")
    monkeypatch.setenv("FCRS_DEBUG", "true")
    monkeypatch.setenv("FCRS_API_PREFIX", "/v1")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Configured API"
    assert settings.app_env is AppEnvironment.TESTING
    assert settings.debug is True
    assert settings.api_prefix == "/v1"


@pytest.mark.parametrize("app_name", ["", "   "])
def test_app_name_cannot_be_empty(app_name: str) -> None:
    with pytest.raises(ValidationError, match="application name cannot be empty"):
        Settings(app_name=app_name, _env_file=None)


@pytest.mark.parametrize("api_prefix", ["api", "api/v1", ""])
def test_api_prefix_must_start_with_slash(api_prefix: str) -> None:
    with pytest.raises(ValidationError, match="API prefix must start"):
        Settings(api_prefix=api_prefix, _env_file=None)


@pytest.mark.parametrize("api_prefix", ["/api/", "/v1/"])
def test_api_prefix_cannot_end_with_slash(api_prefix: str) -> None:
    with pytest.raises(ValidationError, match="API prefix cannot end"):
        Settings(api_prefix=api_prefix, _env_file=None)


def test_root_api_prefix_is_valid() -> None:
    assert Settings(api_prefix="/", _env_file=None).api_prefix == "/"


def test_settings_cache() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_cors_origins_load_normalize_and_deduplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " https://app.example.com/, http://localhost:5173,"
        "https://app.example.com ",
    )

    assert Settings(_env_file=None).cors_allowed_origins == [
        "https://app.example.com",
        "http://localhost:5173",
    ]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("*", "wildcard CORS origins are not supported"),
        ("https://app.example.com,*", "wildcard CORS origins are not supported"),
        ("ftp://app.example.com", "valid HTTP or HTTPS origins"),
        ("app.example.com", "valid HTTP or HTTPS origins"),
        ("https://app.example.com/path", "valid HTTP or HTTPS origins"),
        ("http://localhost:5173,", "blank items"),
        ("", "blank items"),
    ],
)
def test_invalid_cors_origins_are_rejected(value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(cors_allowed_origins=value, _env_file=None)
