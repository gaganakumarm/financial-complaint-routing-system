"""Safe prediction API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ComplaintStatus, ComplaintUrgency, ModelType


class PredictionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_type: ModelType | None = None


class PredictionCategorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str = Field(validation_alias="display_name")


class PredictionDepartmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str = Field(validation_alias="display_name")


class PredictionModelVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str
    version: str


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    complaint_id: UUID
    model_version_id: UUID
    predicted_category_id: UUID | None
    predicted_department_id: UUID | None
    predicted_urgency: ComplaintUrgency | None
    confidence_score: Decimal | None
    output_valid: bool
    failure_code: str | None
    inference_latency_ms: int | None
    created_at: datetime


class ReviewerPredictionResponse(PredictionResponse):
    model_version: PredictionModelVersionSummary
    category: PredictionCategorySummary | None = Field(
        validation_alias="predicted_category"
    )
    department: PredictionDepartmentSummary | None = Field(
        validation_alias="predicted_department"
    )


class PredictionRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prediction: PredictionResponse
    complaint_status: ComplaintStatus


class PredictionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ReviewerPredictionResponse]
    offset: int
    limit: int
    count: int
