"""Reviewer-safe controlled reference-data responses."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ReferenceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ComplaintCategoryReferenceItem(_ReferenceSchema):
    id: UUID
    name: str = Field(validation_alias="display_name")
    description: str | None
    active: bool = Field(validation_alias="is_active")


class ComplaintCategoryReferenceList(_ReferenceSchema):
    items: list[ComplaintCategoryReferenceItem]
    count: int


class DepartmentReferenceItem(_ReferenceSchema):
    id: UUID
    name: str = Field(validation_alias="display_name")
    description: str | None
    active: bool = Field(validation_alias="is_active")


class DepartmentReferenceList(_ReferenceSchema):
    items: list[DepartmentReferenceItem]
    count: int
