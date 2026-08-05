"""Safe request and response schemas for dataset examples."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ComplaintUrgency


class DatasetExampleCreateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    example_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    expected_category_id: UUID
    expected_department_id: UUID
    expected_urgency: ComplaintUrgency

    @field_validator("example_id", "title", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class DatasetExampleBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    examples: list[DatasetExampleCreateItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_example_ids(self):
        ids = [item.example_id for item in self.examples]
        if len(ids) != len(set(ids)):
            raise ValueError("example IDs must be unique")
        return self


class DatasetExampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    dataset_version_id: UUID
    example_id: str
    title: str
    description: str
    expected_category_id: UUID
    expected_department_id: UUID
    expected_urgency: ComplaintUrgency
    created_at: datetime


class DatasetExampleListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DatasetExampleResponse]
    offset: int
    limit: int
    count: int


class DatasetExampleBatchCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DatasetExampleResponse]
    count: int
