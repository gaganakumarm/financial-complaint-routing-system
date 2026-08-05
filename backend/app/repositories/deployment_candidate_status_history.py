"""Transaction-neutral deployment-candidate history persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DeploymentCandidateStatusHistory
from app.repositories.base import BaseRepository


class DeploymentCandidateStatusHistoryRepository(
    BaseRepository[DeploymentCandidateStatusHistory]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DeploymentCandidateStatusHistory)

    async def add_history(
        self, history: DeploymentCandidateStatusHistory
    ) -> DeploymentCandidateStatusHistory:
        if not isinstance(history, DeploymentCandidateStatusHistory):
            raise ValueError("history must be a DeploymentCandidateStatusHistory")
        self.session.add(history)
        return history

    async def list_for_candidate(
        self,
        deployment_candidate_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DeploymentCandidateStatusHistory]:
        self._validate_candidate_id(deployment_candidate_id)
        self._validate_pagination(offset, limit)
        result = await self.session.execute(
            select(DeploymentCandidateStatusHistory)
            .options(selectinload(DeploymentCandidateStatusHistory.changed_by_user))
            .where(
                DeploymentCandidateStatusHistory.deployment_candidate_id
                == deployment_candidate_id
            )
            .order_by(
                DeploymentCandidateStatusHistory.changed_at.asc(),
                DeploymentCandidateStatusHistory.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_for_candidate(
        self, deployment_candidate_id: UUID
    ) -> DeploymentCandidateStatusHistory | None:
        self._validate_candidate_id(deployment_candidate_id)
        result = await self.session.execute(
            select(DeploymentCandidateStatusHistory)
            .options(selectinload(DeploymentCandidateStatusHistory.changed_by_user))
            .where(
                DeploymentCandidateStatusHistory.deployment_candidate_id
                == deployment_candidate_id
            )
            .order_by(
                DeploymentCandidateStatusHistory.changed_at.desc(),
                DeploymentCandidateStatusHistory.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_candidate_id(value: UUID) -> None:
        if not isinstance(value, UUID):
            raise ValueError("deployment_candidate_id must be a UUID")


__all__ = ["DeploymentCandidateStatusHistoryRepository"]
