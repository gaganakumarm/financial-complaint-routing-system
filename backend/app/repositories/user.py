"""User repository."""

from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User
from app.repositories.base import BaseRepository, normalize_required


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_id(self, entity_id: UUID) -> User | None:
        statement = (
            select(User)
            .options(selectinload(User.role))
            .where(User.id == entity_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        normalized = normalize_required(email, "email")
        statement = (
            select(User)
            .options(selectinload(User.role))
            .where(func.lower(User.email) == func.lower(normalized))
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        normalized = normalize_required(email, "email")
        statement = select(
            exists().where(func.lower(User.email) == func.lower(normalized))
        )
        result = await self.session.execute(statement)
        return bool(result.scalar_one())
