"""Human review API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ComplaintStatus, ComplaintUrgency, ReviewOutcome


class _ReviewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ReviewQueueItemResponse(_ReviewSchema):
    complaint_id: UUID = Field(validation_alias="id")
    reference_number: str
    title: str
    current_status: ComplaintStatus
    created_at: datetime
    updated_at: datetime


class ReviewQueueResponse(_ReviewSchema):
    items: list[ReviewQueueItemResponse]
    offset: int
    limit: int
    count: int


class ReviewClaimResponse(_ReviewSchema):
    complaint_id: UUID
    current_status: ComplaintStatus


class ReviewActionRequest(_ReviewSchema):
    prediction_id: UUID
    comment: str | None = Field(default=None, max_length=2_000)


class ReviewCorrectionRequest(ReviewActionRequest):
    category_id: UUID
    department_id: UUID
    urgency: ComplaintUrgency


class ReviewResponse(_ReviewSchema):
    id: UUID
    complaint_id: UUID
    prediction_id: UUID
    reviewer_id: UUID
    outcome: ReviewOutcome
    approved_category_id: UUID | None
    approved_department_id: UUID | None
    approved_urgency: ComplaintUrgency | None
    comments: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
