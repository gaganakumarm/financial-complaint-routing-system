"""Human-review repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, ReviewOutcome
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Review)

    async def get_for_prediction(self, prediction_id: UUID) -> Review | None:
        result = await self.session.execute(
            select(Review).where(Review.prediction_id == prediction_id)
        )
        return result.scalar_one_or_none()

    async def list_for_reviewer(
        self, reviewer_id: UUID, *, offset: int = 0, limit: int = 100
    ) -> list[Review]:
        self._validate_pagination(offset, limit)
        statement = (
            select(Review)
            .where(Review.reviewer_id == reviewer_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_pending(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[Review]:
        self._validate_pagination(offset, limit)
        statement = (
            select(Review)
            .where(Review.outcome == ReviewOutcome.PENDING)
            .order_by(Review.created_at.asc(), Review.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
