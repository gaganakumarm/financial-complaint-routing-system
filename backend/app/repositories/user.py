"""User repository."""

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories.base import BaseRepository, normalize_required


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        normalized = normalize_required(email, "email")
        statement = select(User).where(func.lower(User.email) == func.lower(normalized))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        normalized = normalize_required(email, "email")
        statement = select(
            exists().where(func.lower(User.email) == func.lower(normalized))
        )
        result = await self.session.execute(statement)
        return bool(result.scalar_one())
