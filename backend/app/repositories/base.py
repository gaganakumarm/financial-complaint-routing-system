"""Reusable asynchronous repository primitives."""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class BaseRepository(Generic[ModelT]):
    """Provide transaction-neutral persistence operations for one ORM model."""

    def __init__(self, session: AsyncSession, model_type: type[ModelT]) -> None:
        self.session = session
        self.model_type = model_type

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model_type, entity_id)

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        self._validate_pagination(offset, limit)
        statement = select(self.model_type).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, entity: ModelT) -> ModelT:
        await self.session.refresh(entity)
        return entity

    @staticmethod
    def _validate_pagination(offset: int, limit: int) -> None:
        if offset < 0:
            raise ValueError("offset must be greater than or equal to zero")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")


def normalize_required(value: str, field_name: str) -> str:
    """Trim a required query value and reject blank input."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized
