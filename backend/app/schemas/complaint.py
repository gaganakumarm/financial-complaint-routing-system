"""Customer-facing complaint API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ComplaintStatus, ComplaintUrgency


class _ComplaintSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ComplaintCreateRequest(_ComplaintSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)


class ComplaintResponse(_ComplaintSchema):
    id: UUID
    reference_number: str
    customer_id: UUID
    title: str
    description: str
    current_status: ComplaintStatus
    final_category_id: UUID | None
    final_department_id: UUID | None
    final_urgency: ComplaintUrgency | None
    created_at: datetime
    updated_at: datetime


class ComplaintCreateResponse(_ComplaintSchema):
    complaint: ComplaintResponse


class ComplaintListResponse(_ComplaintSchema):
    items: list[ComplaintResponse]
    offset: int
    limit: int
    count: int
