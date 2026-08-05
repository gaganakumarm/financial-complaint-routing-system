"""Transaction-neutral department lookups."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department
from app.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Department)

    async def get_by_ids(self, entity_ids: Collection[UUID]) -> dict[UUID, Department]:
        identifiers = set(entity_ids)
        if any(not isinstance(identifier, UUID) for identifier in identifiers):
            raise ValueError("department IDs must be UUIDs")
        if not identifiers:
            return {}
        result = await self.session.execute(select(Department).where(Department.id.in_(identifiers)))
        return {item.id: item for item in result.scalars().all()}
