"""Safe dataset-version API schemas."""

from datetime import datetime
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DatasetSplit


class DatasetVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    source_name: str = Field(min_length=1, max_length=200)
    source_reference: str | None = None
    taxonomy_version: str = Field(min_length=1, max_length=50)
    split: DatasetSplit
    record_count: int = Field(gt=0)
    content_hash: str = Field(min_length=1, max_length=128)
    preparation_details: dict[str, Any] | None = None

    @field_validator("name", "version", "source_name", "taxonomy_version", "content_hash")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("source_reference")
    @classmethod
    def normalize_reference(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("preparation_details")
    @classmethod
    def validate_details(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                raise ValueError("preparation_details must be JSON-compatible") from None
        return value


class DatasetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    version: str
    source_name: str
    source_reference: str | None
    taxonomy_version: str
    split: DatasetSplit
    record_count: int
    content_hash: str
    preparation_details: dict[str, Any] | None
    created_at: datetime


class DatasetVersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DatasetVersionResponse]
    offset: int
    limit: int
    count: int
