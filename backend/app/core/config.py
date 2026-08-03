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


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
