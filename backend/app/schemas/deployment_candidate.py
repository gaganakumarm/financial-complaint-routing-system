"""Safe deployment-candidate API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import DeploymentCandidateStatus, ModelPromotionStatus


def _normalize_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError("text must not be blank")
    return normalized


class DeploymentCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_promotion_decision_id: UUID
    notes: str | None = Field(default=None, min_length=1, max_length=10_000)
    _normalize_notes = field_validator("notes", mode="before")(_normalize_text)


class DeploymentCandidateStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, min_length=1, max_length=10_000)
    _normalize_note = field_validator("note", mode="before")(_normalize_text)


class DeploymentCandidateActivateRequest(DeploymentCandidateStageRequest):
    pass


class DeploymentCandidateRetireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retirement_reason: str = Field(min_length=1, max_length=10_000)
    _normalize_reason = field_validator("retirement_reason", mode="before")(_normalize_text)


class DeploymentCandidateRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejection_reason: str = Field(min_length=1, max_length=10_000)
    _normalize_reason = field_validator("rejection_reason", mode="before")(_normalize_text)


class DeploymentCandidatePromotionResponse(BaseModel):
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
    created_at: datetime


class DeploymentCandidateBenchmarkResultResponse(BaseModel):
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


class DeploymentCandidateModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str
    version: str


class DeploymentCandidateUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    email: str
    full_name: str


class DeploymentCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    model_promotion_decision_id: UUID
    benchmark_result_id: UUID
    model_version_id: UUID
    status: DeploymentCandidateStatus
    registered_by_user_id: UUID
    registered_at: datetime
    staged_at: datetime | None
    activated_at: datetime | None
    retired_at: datetime | None
    retirement_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    model_promotion_decision: DeploymentCandidatePromotionResponse
    benchmark_result: DeploymentCandidateBenchmarkResultResponse
    model_version: DeploymentCandidateModelVersionResponse
    registered_by_user: DeploymentCandidateUserResponse


class DeploymentCandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DeploymentCandidateResponse]
    offset: int
    limit: int
    count: int


__all__ = [name for name in globals() if name.startswith("DeploymentCandidate")]
