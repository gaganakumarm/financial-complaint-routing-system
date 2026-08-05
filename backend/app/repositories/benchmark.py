"""Dataset and benchmark repositories."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BenchmarkExperiment,
    BenchmarkExperimentStatus,
    BenchmarkResult,
    BenchmarkExampleResult,
    DatasetSplit,
    DatasetVersion,
)
from app.repositories.base import BaseRepository, normalize_required


class DatasetVersionRepository(BaseRepository[DatasetVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DatasetVersion)

    async def get_by_identity(
        self, *, name: str, version: str, split: DatasetSplit
    ) -> DatasetVersion | None:
        normalized_name = normalize_required(name, "name")
        normalized_version = normalize_required(version, "version")
        result = await self.session.execute(
            select(DatasetVersion).where(
                DatasetVersion.name == normalized_name,
                DatasetVersion.version == normalized_version,
                DatasetVersion.split == split,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_content_hash(self, content_hash: str) -> DatasetVersion | None:
        normalized = normalize_required(content_hash, "content_hash")
        result = await self.session.execute(
            select(DatasetVersion).where(DatasetVersion.content_hash == normalized)
        )
        return result.scalar_one_or_none()


class BenchmarkExperimentRepository(BaseRepository[BenchmarkExperiment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BenchmarkExperiment)

    async def list_by_status(
        self,
        status: BenchmarkExperimentStatus,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BenchmarkExperiment]:
        return await self._list_where(
            BenchmarkExperiment.status == status, offset=offset, limit=limit
        )

    async def list_for_dataset(
        self,
        dataset_version_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[BenchmarkExperiment]:
        return await self._list_where(
            BenchmarkExperiment.dataset_version_id == dataset_version_id,
            offset=offset,
            limit=limit,
        )

    async def _list_where(
        self, criterion, *, offset: int, limit: int
    ) -> list[BenchmarkExperiment]:
        self._validate_pagination(offset, limit)
        statement = (
            select(BenchmarkExperiment)
            .where(criterion)
            .order_by(BenchmarkExperiment.created_at.desc(), BenchmarkExperiment.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class BenchmarkResultRepository(BaseRepository[BenchmarkResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BenchmarkResult)

    async def get_for_experiment_and_model(
        self, *, experiment_id: UUID, model_version_id: UUID
    ) -> BenchmarkResult | None:
        result = await self.session.execute(
            select(BenchmarkResult).where(
                BenchmarkResult.benchmark_experiment_id == experiment_id,
                BenchmarkResult.model_version_id == model_version_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_experiment(
        self, experiment_id: UUID
    ) -> list[BenchmarkResult]:
        statement = (
            select(BenchmarkResult)
            .where(BenchmarkResult.benchmark_experiment_id == experiment_id)
            .order_by(BenchmarkResult.created_at.asc(), BenchmarkResult.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_with_outcomes(self, result_id: UUID) -> BenchmarkResult | None:
        if not isinstance(result_id, UUID):
            raise ValueError("result_id must be a UUID")
        result = await self.session.execute(select(BenchmarkResult).options(selectinload(BenchmarkResult.example_results)).where(BenchmarkResult.id == result_id))
        return result.scalar_one_or_none()

    async def get_results_by_ids(
        self, benchmark_result_ids: Collection[UUID]
    ) -> list[BenchmarkResult]:
        if isinstance(benchmark_result_ids, (str, bytes)) or not isinstance(
            benchmark_result_ids, Collection
        ):
            raise ValueError("benchmark_result_ids must be a collection of UUIDs")
        if any(not isinstance(identifier, UUID) for identifier in benchmark_result_ids):
            raise ValueError("benchmark_result_ids must contain only UUIDs")
        identifiers = set(benchmark_result_ids)
        if not identifiers:
            return []
        statement = (
            select(BenchmarkResult)
            .options(
                selectinload(BenchmarkResult.experiment).selectinload(
                    BenchmarkExperiment.dataset_version
                ),
                selectinload(BenchmarkResult.model_version),
            )
            .where(BenchmarkResult.id.in_(identifiers))
            .order_by(BenchmarkResult.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class BenchmarkExampleResultRepository(BaseRepository[BenchmarkExampleResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BenchmarkExampleResult)

    async def list_for_result(self, result_id: UUID) -> list[BenchmarkExampleResult]:
        if not isinstance(result_id, UUID):
            raise ValueError("result_id must be a UUID")
        result = await self.session.execute(select(BenchmarkExampleResult).where(BenchmarkExampleResult.benchmark_result_id == result_id).order_by(BenchmarkExampleResult.created_at.asc(), BenchmarkExampleResult.id.asc()))
        return list(result.scalars().all())
