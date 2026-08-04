"""Typed application configuration."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
