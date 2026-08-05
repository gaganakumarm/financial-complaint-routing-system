"""Safe benchmark-comparison API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BenchmarkExperimentStatus


class BenchmarkComparisonCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_result_ids: list[UUID] = Field(min_length=2, max_length=10)
    ranking_metric: str = Field(min_length=1, max_length=100)

    @field_validator("benchmark_result_ids")
    @classmethod
    def unique_result_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("benchmark result IDs must be unique")
        return value

    @field_validator("ranking_metric", mode="before")
    @classmethod
    def normalize_ranking_metric(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("ranking metric must not be blank")
        return normalized


class BenchmarkComparisonModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str
    version: str


class BenchmarkComparisonExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    name: str
    status: BenchmarkExperimentStatus


class BenchmarkComparisonResultResponse(BaseModel):
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
    model_version: BenchmarkComparisonModelVersionResponse
    experiment: BenchmarkComparisonExperimentResponse


class BenchmarkComparisonMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    benchmark_comparison_id: UUID
    benchmark_result_id: UUID
    rank: int
    created_at: datetime
    benchmark_result: BenchmarkComparisonResultResponse


class BenchmarkComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    dataset_version_id: UUID
    dataset_checksum: str
    dataset_example_count: int
    winner_result_id: UUID
    ranking_metric: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    members: list[BenchmarkComparisonMemberResponse]

    @field_validator("members")
    @classmethod
    def order_members(
        cls, value: list[BenchmarkComparisonMemberResponse]
    ) -> list[BenchmarkComparisonMemberResponse]:
        return sorted(value, key=lambda member: (member.rank, member.id))


class BenchmarkComparisonListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BenchmarkComparisonResponse]
    offset: int
    limit: int
    count: int


__all__ = [
    "BenchmarkComparisonCreateRequest",
    "BenchmarkComparisonExperimentResponse",
    "BenchmarkComparisonListResponse",
    "BenchmarkComparisonMemberResponse",
    "BenchmarkComparisonModelVersionResponse",
    "BenchmarkComparisonResponse",
    "BenchmarkComparisonResultResponse",
]
