"""Safe benchmark REST API schemas."""

from datetime import datetime
from decimal import Decimal
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BenchmarkExperimentStatus


class BenchmarkExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version_id: UUID
    name: str = Field(min_length=1, max_length=200)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("configuration must be JSON-compatible") from None
        return value


class BenchmarkExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    dataset_version_id: UUID
    name: str
    status: BenchmarkExperimentStatus
    configuration: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    failure_message: str | None
    created_at: datetime


class BenchmarkExperimentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BenchmarkExperimentResponse]
    offset: int
    limit: int
    count: int


class BenchmarkResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    benchmark_experiment_id: UUID
    model_version_id: UUID
    sample_count: int
    accuracy: Decimal | None
    macro_precision: Decimal | None
    macro_recall: Decimal | None
    macro_f1: Decimal | None
    cost_weighted_error: Decimal | None
    structured_output_validity_rate: Decimal | None
    average_inference_latency_ms: Decimal | None
    throughput_per_second: Decimal | None
    estimated_cost: Decimal | None
    per_class_metrics: dict[str, Any] | None
    additional_metrics: dict[str, Any] | None
    created_at: datetime


class BenchmarkResultListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BenchmarkResultResponse]
    offset: int
    limit: int
    count: int
