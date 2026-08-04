"""Complaint repository."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Complaint, ComplaintStatus
from app.repositories.base import BaseRepository, normalize_required


class ComplaintRepository(BaseRepository[Complaint]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Complaint)

    async def get_by_reference_number(self, reference_number: str) -> Complaint | None:
        normalized = normalize_required(reference_number, "reference_number")
        result = await self.session.execute(
            select(Complaint).where(Complaint.reference_number == normalized)
        )
        return result.scalar_one_or_none()

    async def list_for_customer(
        self, customer_id: UUID, *, offset: int = 0, limit: int = 100
    ) -> list[Complaint]:
        self._validate_pagination(offset, limit)
        statement = (
            select(Complaint)
            .where(Complaint.customer_id == customer_id)
            .order_by(Complaint.created_at.desc(), Complaint.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_review_queue(
        self,
        *,
        statuses: Sequence[ComplaintStatus] | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Complaint]:
        self._validate_pagination(offset, limit)
        selected_statuses = (
            (ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.UNDER_REVIEW)
            if statuses is None
            else tuple(statuses)
        )
        if not selected_statuses:
            raise ValueError("statuses cannot be empty")
        statement = (
            select(Complaint)
            .where(Complaint.current_status.in_(selected_statuses))
            .order_by(Complaint.created_at.asc(), Complaint.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
