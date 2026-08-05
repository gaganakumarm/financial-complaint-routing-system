"""Transaction-neutral repositories used by dataset example ingestion."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DatasetExample
from app.repositories.base import BaseRepository, normalize_required


def _uuid(value: UUID, name: str) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be a UUID")
    return value


class DatasetExampleRepository(BaseRepository[DatasetExample]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DatasetExample)

    async def get_for_dataset_and_example_id(self, *, dataset_version_id: UUID, example_id: str) -> DatasetExample | None:
        dataset_id = _uuid(dataset_version_id, "dataset_version_id")
        normalized = normalize_required(example_id, "example_id")
        result = await self.session.execute(select(DatasetExample).where(DatasetExample.dataset_version_id == dataset_id, DatasetExample.example_id == normalized))
        return result.scalar_one_or_none()

    async def list_for_dataset(self, dataset_version_id: UUID, *, offset: int = 0, limit: int = 100) -> list[DatasetExample]:
        dataset_id = _uuid(dataset_version_id, "dataset_version_id")
        self._validate_pagination(offset, limit)
        result = await self.session.execute(select(DatasetExample).where(DatasetExample.dataset_version_id == dataset_id).order_by(DatasetExample.created_at.asc(), DatasetExample.id.asc()).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def count_for_dataset(self, dataset_version_id: UUID) -> int:
        dataset_id = _uuid(dataset_version_id, "dataset_version_id")
        result = await self.session.execute(select(func.count()).select_from(DatasetExample).where(DatasetExample.dataset_version_id == dataset_id))
        return int(result.scalar_one())

    async def list_all_for_dataset(self, dataset_version_id: UUID) -> list[DatasetExample]:
        dataset_id = _uuid(dataset_version_id, "dataset_version_id")
        result = await self.session.execute(select(DatasetExample).where(DatasetExample.dataset_version_id == dataset_id).order_by(DatasetExample.example_id.asc(), DatasetExample.id.asc()))
        return list(result.scalars().all())

    async def example_ids_exist(self, *, dataset_version_id: UUID, example_ids: Collection[str]) -> set[str]:
        dataset_id = _uuid(dataset_version_id, "dataset_version_id")
        normalized = {normalize_required(value, "example_id") for value in example_ids}
        if not normalized:
            return set()
        result = await self.session.execute(select(DatasetExample.example_id).where(DatasetExample.dataset_version_id == dataset_id, DatasetExample.example_id.in_(normalized)))
        return set(result.scalars().all())
