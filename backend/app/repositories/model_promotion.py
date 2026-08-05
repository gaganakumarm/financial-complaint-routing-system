"""Transaction-neutral model-promotion persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    BenchmarkComparison,
    BenchmarkComparisonMember,
    BenchmarkExperiment,
    BenchmarkResult,
    ModelPromotionDecision,
    ModelPromotionStatus,
)
from app.repositories.base import BaseRepository


class ModelPromotionRepository(BaseRepository[ModelPromotionDecision]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ModelPromotionDecision)

    async def get_by_id(self, promotion_id: UUID) -> ModelPromotionDecision | None:
        self._validate_uuid(promotion_id, "promotion_id")
        return await self.session.get(ModelPromotionDecision, promotion_id)

    async def get_with_details(
        self, promotion_id: UUID
    ) -> ModelPromotionDecision | None:
        self._validate_uuid(promotion_id, "promotion_id")
        result = await self.session.execute(
            select(ModelPromotionDecision)
            .options(*self._detail_options())
            .where(ModelPromotionDecision.id == promotion_id)
        )
        promotion = result.scalar_one_or_none()
        if promotion is not None:
            promotion.benchmark_comparison.members.sort(
                key=lambda member: (member.rank, member.id)
            )
        return promotion

    async def list_promotions(
        self,
        *,
        status: ModelPromotionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ModelPromotionDecision]:
        self._validate_pagination(offset, limit)
        if status is not None and not isinstance(status, ModelPromotionStatus):
            raise ValueError("status must be a ModelPromotionStatus")
        statement = (
            select(ModelPromotionDecision)
            .options(
                selectinload(ModelPromotionDecision.benchmark_comparison),
                selectinload(ModelPromotionDecision.selected_benchmark_result),
                selectinload(ModelPromotionDecision.selected_model_version),
                selectinload(ModelPromotionDecision.requested_by_user),
                selectinload(ModelPromotionDecision.reviewed_by_user),
            )
            .order_by(
                ModelPromotionDecision.requested_at.desc(),
                ModelPromotionDecision.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(ModelPromotionDecision.status == status)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_pending_for_comparison(
        self, benchmark_comparison_id: UUID
    ) -> ModelPromotionDecision | None:
        self._validate_uuid(benchmark_comparison_id, "benchmark_comparison_id")
        result = await self.session.execute(
            select(ModelPromotionDecision).where(
                ModelPromotionDecision.benchmark_comparison_id
                == benchmark_comparison_id,
                ModelPromotionDecision.status == ModelPromotionStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def add_promotion(
        self, promotion: ModelPromotionDecision
    ) -> ModelPromotionDecision:
        self.session.add(promotion)
        return promotion

    @staticmethod
    def _validate_uuid(value: UUID, field_name: str) -> None:
        if not isinstance(value, UUID):
            raise ValueError(f"{field_name} must be a UUID")

    @staticmethod
    def _detail_options():
        comparison_members = (
            selectinload(ModelPromotionDecision.benchmark_comparison)
            .selectinload(BenchmarkComparison.members)
            .selectinload(BenchmarkComparisonMember.benchmark_result)
        )
        return (
            comparison_members
            .selectinload(BenchmarkResult.experiment)
            .selectinload(BenchmarkExperiment.dataset_version),
            comparison_members.selectinload(BenchmarkResult.model_version),
            selectinload(ModelPromotionDecision.selected_benchmark_result)
            .selectinload(BenchmarkResult.experiment)
            .selectinload(BenchmarkExperiment.dataset_version),
            selectinload(ModelPromotionDecision.selected_benchmark_result)
            .selectinload(BenchmarkResult.model_version),
            selectinload(ModelPromotionDecision.selected_model_version),
            selectinload(ModelPromotionDecision.requested_by_user),
            selectinload(ModelPromotionDecision.reviewed_by_user),
        )


__all__ = ["ModelPromotionRepository"]
