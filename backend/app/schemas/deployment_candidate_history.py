"""Safe deployment-candidate audit-history API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import DeploymentCandidateStatus


class DeploymentCandidateHistoryUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    email: str
    full_name: str


class DeploymentCandidateStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: UUID
    deployment_candidate_id: UUID
    previous_status: DeploymentCandidateStatus | None
    new_status: DeploymentCandidateStatus
    changed_by_user_id: UUID
    note: str | None
    changed_at: datetime
    changed_by_user: DeploymentCandidateHistoryUserResponse


class DeploymentCandidateStatusHistoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DeploymentCandidateStatusHistoryResponse]
    offset: int
    limit: int
    count: int


__all__ = [
    "DeploymentCandidateHistoryUserResponse",
    "DeploymentCandidateStatusHistoryListResponse",
    "DeploymentCandidateStatusHistoryResponse",
]
