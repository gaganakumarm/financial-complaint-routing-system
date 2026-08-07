"""Typed application configuration."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported application runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_prefix="FCRS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Financial Complaint Routing System API"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    debug: bool = False
    api_prefix: str = "/api"
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        validation_alias="CORS_ALLOWED_ORIGINS",
    )
    database_url: str = Field(
        default=(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/"
            "financial_complaints"
        ),
        validation_alias="DATABASE_URL",
    )
    jwt_secret_key: str = Field(
        default="development-only-change-me-please-replace",
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("application name cannot be empty")
        return value

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError('API prefix must start with "/"')
        if value != "/" and value.endswith("/"):
            raise ValueError('API prefix cannot end with "/" unless it is exactly "/"')
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return value.split(",")
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, values: list[str]) -> list[str]:
        normalized_origins: list[str] = []
        for value in values:
            origin = value.strip().rstrip("/")
            if not origin:
                raise ValueError("CORS origins cannot contain blank items")
            if origin == "*":
                raise ValueError("wildcard CORS origins are not supported")

            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError:
                raise ValueError("CORS origins must contain a valid port") from None
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be valid HTTP or HTTPS origins")
            if origin not in normalized_origins:
                normalized_origins.append(origin)

        if not normalized_origins:
            raise ValueError("at least one CORS origin is required")
        return normalized_origins

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("database URL cannot be empty")
        if not normalized_value.startswith("postgresql+asyncpg://"):
            raise ValueError('database URL must start with "postgresql+asyncpg://"')
        return normalized_value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("JWT secret key cannot be blank")
        if len(normalized_value) < 32:
            raise ValueError("JWT secret key must contain at least 32 characters")
        return normalized_value

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        normalized_value = value.strip()
        if normalized_value != "HS256":
            raise ValueError("JWT algorithm must be HS256")
        return normalized_value


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
