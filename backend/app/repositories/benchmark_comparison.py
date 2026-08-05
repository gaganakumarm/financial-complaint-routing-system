"""Transaction-neutral benchmark comparison persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    BenchmarkComparison,
    BenchmarkComparisonMember,
    BenchmarkExperiment,
    BenchmarkResult,
)
from app.repositories.base import BaseRepository


class BenchmarkComparisonRepository(BaseRepository[BenchmarkComparison]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BenchmarkComparison)

    async def get_by_id(self, comparison_id: UUID) -> BenchmarkComparison | None:
        self._validate_uuid(comparison_id)
        return await self.session.get(BenchmarkComparison, comparison_id)

    async def get_with_members(
        self, comparison_id: UUID
    ) -> BenchmarkComparison | None:
        self._validate_uuid(comparison_id)
        statement = (
            select(BenchmarkComparison)
            .options(
                selectinload(BenchmarkComparison.members)
                .selectinload(BenchmarkComparisonMember.benchmark_result)
                .selectinload(BenchmarkResult.experiment)
                .selectinload(BenchmarkExperiment.dataset_version),
                selectinload(BenchmarkComparison.members)
                .selectinload(BenchmarkComparisonMember.benchmark_result)
                .selectinload(BenchmarkResult.model_version),
            )
            .where(BenchmarkComparison.id == comparison_id)
        )
        result = await self.session.execute(statement)
        comparison = result.scalar_one_or_none()
        if comparison is not None:
            comparison.members.sort(key=lambda member: (member.rank, member.id))
        return comparison

    async def list_comparisons(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[BenchmarkComparison]:
        self._validate_pagination(offset, limit)
        statement = (
            select(BenchmarkComparison)
            .options(
                selectinload(BenchmarkComparison.members)
                .selectinload(BenchmarkComparisonMember.benchmark_result)
                .selectinload(BenchmarkResult.experiment)
                .selectinload(BenchmarkExperiment.dataset_version),
                selectinload(BenchmarkComparison.members)
                .selectinload(BenchmarkComparisonMember.benchmark_result)
                .selectinload(BenchmarkResult.model_version),
            )
            .order_by(BenchmarkComparison.created_at.desc(), BenchmarkComparison.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        comparisons = list(result.scalars().all())
        for comparison in comparisons:
            comparison.members.sort(key=lambda member: (member.rank, member.id))
        return comparisons

    async def add_comparison(
        self, comparison: BenchmarkComparison
    ) -> BenchmarkComparison:
        self.session.add(comparison)
        return comparison

    async def add_member(
        self, member: BenchmarkComparisonMember
    ) -> BenchmarkComparisonMember:
        self.session.add(member)
        return member

    async def add_members(
        self, members: list[BenchmarkComparisonMember]
    ) -> list[BenchmarkComparisonMember]:
        self.session.add_all(members)
        return members

    @staticmethod
    def _validate_uuid(value: UUID) -> None:
        if not isinstance(value, UUID):
            raise ValueError("comparison_id must be a UUID")


__all__ = ["BenchmarkComparisonRepository"]
