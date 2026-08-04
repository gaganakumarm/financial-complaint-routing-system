"""Model-version repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelVersion
from app.repositories.base import BaseRepository, normalize_required


class ModelVersionRepository(BaseRepository[ModelVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ModelVersion)

    async def get_by_name_and_version(
        self, name: str, version: str
    ) -> ModelVersion | None:
        normalized_name = normalize_required(name, "name")
        normalized_version = normalize_required(version, "version")
        statement = select(ModelVersion).where(
            ModelVersion.name == normalized_name,
            ModelVersion.version == normalized_version,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active(self) -> ModelVersion | None:
        result = await self.session.execute(
            select(ModelVersion).where(ModelVersion.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_approved(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[ModelVersion]:
        self._validate_pagination(offset, limit)
        statement = (
            select(ModelVersion)
            .where(ModelVersion.is_approved.is_(True))
            .order_by(ModelVersion.created_at.desc(), ModelVersion.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
