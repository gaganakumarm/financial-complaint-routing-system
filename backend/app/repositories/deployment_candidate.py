"""Transaction-neutral deployment-candidate persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DeploymentCandidate, DeploymentCandidateStatus, ModelPromotionDecision
from app.repositories.base import BaseRepository


class DeploymentCandidateRepository(BaseRepository[DeploymentCandidate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DeploymentCandidate)

    async def get_by_id(self, candidate_id: UUID) -> DeploymentCandidate | None:
        self._uuid(candidate_id, "candidate_id")
        return await self.session.get(DeploymentCandidate, candidate_id)

    async def get_with_details(self, candidate_id: UUID) -> DeploymentCandidate | None:
        self._uuid(candidate_id, "candidate_id")
        result = await self.session.execute(
            select(DeploymentCandidate)
            .options(*self._detail_options())
            .where(DeploymentCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def get_for_promotion(self, promotion_id: UUID) -> DeploymentCandidate | None:
        self._uuid(promotion_id, "promotion_id")
        result = await self.session.execute(
            select(DeploymentCandidate).where(
                DeploymentCandidate.model_promotion_decision_id == promotion_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active_candidate(self) -> DeploymentCandidate | None:
        result = await self.session.execute(
            select(DeploymentCandidate)
            .options(*self._detail_options())
            .where(DeploymentCandidate.status == DeploymentCandidateStatus.ACTIVE)
        )
        return result.scalar_one_or_none()

    async def list_candidates(
        self,
        *,
        status: DeploymentCandidateStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DeploymentCandidate]:
        self._validate_pagination(offset, limit)
        if status is not None and not isinstance(status, DeploymentCandidateStatus):
            raise ValueError("status must be a DeploymentCandidateStatus")
        statement = (
            select(DeploymentCandidate)
            .options(*self._detail_options())
            .order_by(DeploymentCandidate.registered_at.desc(), DeploymentCandidate.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(DeploymentCandidate.status == status)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def add_candidate(self, candidate: DeploymentCandidate) -> DeploymentCandidate:
        self.session.add(candidate)
        return candidate

    @staticmethod
    def _uuid(value: UUID, field_name: str) -> None:
        if not isinstance(value, UUID):
            raise ValueError(f"{field_name} must be a UUID")

    @staticmethod
    def _detail_options():
        return (
            selectinload(DeploymentCandidate.model_promotion_decision)
            .selectinload(ModelPromotionDecision.selected_benchmark_result),
            selectinload(DeploymentCandidate.model_promotion_decision)
            .selectinload(ModelPromotionDecision.selected_model_version),
            selectinload(DeploymentCandidate.benchmark_result),
            selectinload(DeploymentCandidate.model_version),
            selectinload(DeploymentCandidate.registered_by_user),
        )


__all__ = ["DeploymentCandidateRepository"]
