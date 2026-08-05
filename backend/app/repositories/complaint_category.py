"""Transaction-neutral complaint category lookups."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ComplaintCategory
from app.repositories.base import BaseRepository


class ComplaintCategoryRepository(BaseRepository[ComplaintCategory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ComplaintCategory)

    async def get_by_ids(self, entity_ids: Collection[UUID]) -> dict[UUID, ComplaintCategory]:
        identifiers = set(entity_ids)
        if any(not isinstance(identifier, UUID) for identifier in identifiers):
            raise ValueError("category IDs must be UUIDs")
        if not identifiers:
            return {}
        result = await self.session.execute(select(ComplaintCategory).where(ComplaintCategory.id.in_(identifiers)))
        return {item.id: item for item in result.scalars().all()}
