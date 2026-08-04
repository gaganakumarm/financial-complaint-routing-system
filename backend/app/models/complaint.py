"""Complaint lifecycle model and enums."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.complaint_category import ComplaintCategory
    from app.models.complaint_status_history import ComplaintStatusHistory
    from app.models.department import Department
    from app.models.user import User


class ComplaintStatus(StrEnum):
    """Complaint lifecycle states persisted as lowercase values."""

    SUBMITTED = "submitted"
    PREDICTION_PENDING = "prediction_pending"
    PREDICTION_COMPLETED = "prediction_completed"
    AWAITING_REVIEW = "awaiting_review"
    UNDER_REVIEW = "under_review"
    ROUTED = "routed"
    CLOSED = "closed"
    PREDICTION_FAILED = "prediction_failed"


class ComplaintUrgency(StrEnum):
    """Final complaint urgency levels persisted as lowercase values."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def complaint_status_enum() -> Enum:
    """Build the shared native complaint-status enum mapping."""
    return Enum(
        ComplaintStatus,
        name="complaint_status",
        values_callable=lambda members: [member.value for member in members],
    )


def complaint_urgency_enum() -> Enum:
    """Build the native complaint-urgency enum mapping."""
    return Enum(
        ComplaintUrgency,
        name="complaint_urgency",
        values_callable=lambda members: [member.value for member in members],
    )


class Complaint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer-submitted financial complaint and its final routing state."""

    __tablename__ = "complaints"

    reference_number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_complaints_customer_id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    current_status: Mapped[ComplaintStatus] = mapped_column(
        complaint_status_enum(),
        default=ComplaintStatus.SUBMITTED,
        server_default=ComplaintStatus.SUBMITTED.value,
        nullable=False,
    )
    final_category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "complaint_categories.id",
            name="fk_complaints_final_category_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    final_department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "departments.id",
            name="fk_complaints_final_department_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    final_urgency: Mapped[ComplaintUrgency | None] = mapped_column(
        complaint_urgency_enum(),
        nullable=True,
    )
    review_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "btrim(reference_number) <> ''",
            name="ck_complaints_reference_number_not_blank",
        ),
        CheckConstraint("btrim(title) <> ''", name="ck_complaints_title_not_blank"),
        CheckConstraint(
            "btrim(description) <> ''",
            name="ck_complaints_description_not_blank",
        ),
        CheckConstraint(
            "review_completed_at IS NULL OR review_started_at IS NULL "
            "OR review_completed_at >= review_started_at",
            name="ck_complaints_review_timestamps_order",
        ),
        CheckConstraint(
            "current_status <> 'routed' OR "
            "(final_category_id IS NOT NULL AND final_department_id IS NOT NULL "
            "AND final_urgency IS NOT NULL)",
            name="ck_complaints_routed_requires_final_routing",
        ),
        Index("uq_complaints_reference_number", "reference_number", unique=True),
        Index("ix_complaints_customer_id", "customer_id"),
        Index("ix_complaints_customer_created_at", "customer_id", "created_at"),
        Index("ix_complaints_review_queue", "current_status", "created_at"),
        Index("ix_complaints_final_category_id", "final_category_id"),
        Index("ix_complaints_final_department_id", "final_department_id"),
    )

    customer: Mapped[User] = relationship(
        back_populates="submitted_complaints",
        foreign_keys=[customer_id],
    )
    final_category: Mapped[ComplaintCategory | None] = relationship(
        back_populates="complaints",
        foreign_keys=[final_category_id],
    )
    final_department: Mapped[Department | None] = relationship(
        back_populates="complaints",
        foreign_keys=[final_department_id],
    )
    status_history: Mapped[list[ComplaintStatusHistory]] = relationship(
        back_populates="complaint"
    )
