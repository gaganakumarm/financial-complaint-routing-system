"""Append-only complaint status history model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.complaint import ComplaintStatus, complaint_status_enum

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.user import User


class ComplaintChangeSource(StrEnum):
    """Origins of complaint status changes persisted as lowercase values."""

    CUSTOMER = "customer"
    REVIEWER = "reviewer"
    ADMINISTRATOR = "administrator"
    SYSTEM = "system"
    MODEL_PIPELINE = "model_pipeline"


def complaint_change_source_enum() -> Enum:
    """Build the native complaint-change-source enum mapping."""
    return Enum(
        ComplaintChangeSource,
        name="complaint_change_source",
        values_callable=lambda members: [member.value for member in members],
    )


class ComplaintStatusHistory(UUIDPrimaryKeyMixin, Base):
    """An append-only record of a complaint status transition."""

    __tablename__ = "complaint_status_history"

    complaint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "complaints.id",
            name="fk_complaint_status_history_complaint_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    previous_status: Mapped[ComplaintStatus | None] = mapped_column(
        complaint_status_enum(),
        nullable=True,
    )
    new_status: Mapped[ComplaintStatus] = mapped_column(
        complaint_status_enum(),
        nullable=False,
    )
    changed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_complaint_status_history_changed_by_user_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    change_source: Mapped[ComplaintChangeSource] = mapped_column(
        complaint_change_source_enum(),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_complaint_status_history_complaint_created_at",
            "complaint_id",
            "created_at",
        ),
        Index(
            "ix_complaint_status_history_changed_by_user_id",
            "changed_by_user_id",
        ),
    )

    complaint: Mapped[Complaint] = relationship(back_populates="status_history")
    changed_by_user: Mapped[User | None] = relationship(
        back_populates="complaint_status_changes",
        foreign_keys=[changed_by_user_id],
    )
