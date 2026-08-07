"""Pydantic schemas for authentication API workflows."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasPath, BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128, repr=False)
    full_name: str = Field(min_length=1, max_length=200)
    role_id: UUID


class LoginRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128, repr=False)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    role_id: UUID
    role_name: str = Field(validation_alias=AliasPath("role", "name"))
    email: str
    full_name: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    access_token: str
    token_type: Literal["bearer"]

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("access token cannot be blank")
        return value


class RegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    user: UserResponse


class ErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    detail: str
