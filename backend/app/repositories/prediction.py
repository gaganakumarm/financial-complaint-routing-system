"""Prediction repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Prediction
from app.repositories.base import BaseRepository


class PredictionRepository(BaseRepository[Prediction]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Prediction)

    async def list_for_complaint(
        self, complaint_id: UUID, *, offset: int = 0, limit: int = 100
    ) -> list[Prediction]:
        self._validate_pagination(offset, limit)
        statement = (
            select(Prediction)
            .where(Prediction.complaint_id == complaint_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_latest_for_complaint(self, complaint_id: UUID) -> Prediction | None:
        statement = (
            select(Prediction)
            .where(Prediction.complaint_id == complaint_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
