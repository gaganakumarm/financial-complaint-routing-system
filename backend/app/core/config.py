"""Typed application configuration."""

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
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
    )

    app_name: str = "Financial Complaint Routing System API"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    debug: bool = False
    api_prefix: str = "/api"

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


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
