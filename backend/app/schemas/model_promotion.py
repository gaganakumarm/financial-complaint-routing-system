"""Safe model-promotion API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.models import ModelPromotionStatus


def _normalize_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError("text must not be blank")
    return normalized


class ModelPromotionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benchmark_comparison_id: UUID
    selected_benchmark_result_id: UUID
    rationale: str = Field(min_length=1, max_length=10_000)
    override_winner: StrictBool = False

    _normalize_rationale = field_validator("rationale", mode="before")(_normalize_text)


class ModelPromotionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: str = Field(min_length=1, max_length=10_000)
    _normalize_note = field_validator("review_note", mode="before")(_normalize_text)


class ModelPromotionCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cancellation_note: str = Field(min_length=1, max_length=10_000)
    _normalize_note = field_validator("cancellation_note", mode="before")(_normalize_text)


class ModelPromotionBenchmarkResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    benchmark_experiment_id: UUID
    model_version_id: UUID
    sample_count: int
    total_error_cost: Decimal | None
    exact_match_accuracy: Decimal | None
    failed_prediction_count: int | None
    department_accuracy: Decimal | None
    category_accuracy: Decimal | None
    urgency_accuracy: Decimal | None
    p95_inference_latency_ms: int | None
    average_inference_latency_ms: Decimal | None
    cost_weighted_error: Decimal | None
    created_at: datetime


class ModelPromotionComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    dataset_version_id: UUID
    winner_result_id: UUID
    ranking_metric: str
    created_at: datetime


class ModelPromotionModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str
    version: str


class ModelPromotionUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    email: str
    full_name: str


class ModelPromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    benchmark_comparison_id: UUID
    selected_benchmark_result_id: UUID
    selected_model_version_id: UUID
    status: ModelPromotionStatus
    rationale: str
    override_winner: bool
    requested_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    requested_at: datetime
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime
    benchmark_comparison: ModelPromotionComparisonResponse
    selected_benchmark_result: ModelPromotionBenchmarkResultResponse
    selected_model_version: ModelPromotionModelVersionResponse
    requested_by_user: ModelPromotionUserResponse
    reviewed_by_user: ModelPromotionUserResponse | None


class ModelPromotionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ModelPromotionResponse]
    offset: int
    limit: int
    count: int


__all__ = [
    "ModelPromotionBenchmarkResultResponse",
    "ModelPromotionCancelRequest",
    "ModelPromotionComparisonResponse",
    "ModelPromotionCreateRequest",
    "ModelPromotionListResponse",
    "ModelPromotionModelVersionResponse",
    "ModelPromotionResponse",
    "ModelPromotionReviewRequest",
    "ModelPromotionUserResponse",
]
