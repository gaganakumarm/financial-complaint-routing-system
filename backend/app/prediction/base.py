"""Contracts for future complaint prediction implementations."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.models import Complaint, ComplaintUrgency, ModelVersion


@dataclass(frozen=True, slots=True)
class PredictionOutput:
    category_id: UUID
    department_id: UUID
    confidence_score: float
    urgency: ComplaintUrgency
    raw_output: dict[str, object] | None = None


@runtime_checkable
class ComplaintPredictor(Protocol):
    async def predict(
        self,
        *,
        complaint: Complaint,
        model_version: ModelVersion,
    ) -> PredictionOutput: ...
