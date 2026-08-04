"""Human review persistence model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.complaint import ComplaintUrgency, complaint_urgency_enum

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.complaint_category import ComplaintCategory
    from app.models.department import Department
    from app.models.prediction import Prediction
    from app.models.user import User


class ReviewOutcome(StrEnum):
    """Human review outcomes persisted as lowercase values."""

    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


def review_outcome_enum() -> Enum:
    """Build the native review-outcome enum mapping."""
    return Enum(
        ReviewOutcome,
        name="review_outcome",
        values_callable=lambda members: [member.value for member in members],
    )


class Review(UUIDPrimaryKeyMixin, Base):
    """One reviewer decision that validates or corrects an immutable prediction.

    Matching ``complaint_id`` to the prediction's complaint is a future
    application/service-layer invariant because a database check constraint
    cannot reference the prediction table.
    """

    __tablename__ = "reviews"

    complaint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("complaints.id", name="fk_reviews_complaint_id", ondelete="RESTRICT"),
        nullable=False,
    )
    prediction_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("predictions.id", name="fk_reviews_prediction_id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_reviews_reviewer_id", ondelete="RESTRICT"),
        nullable=False,
    )
    outcome: Mapped[ReviewOutcome] = mapped_column(
        review_outcome_enum(),
        default=ReviewOutcome.PENDING,
        server_default=ReviewOutcome.PENDING.value,
        nullable=False,
    )
    approved_category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "complaint_categories.id",
            name="fk_reviews_approved_category_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    approved_department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "departments.id",
            name="fk_reviews_approved_department_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    approved_urgency: Mapped[ComplaintUrgency | None] = mapped_column(
        complaint_urgency_enum(),
        nullable=True,
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_reviews_completion_timestamps_order",
        ),
        CheckConstraint(
            "outcome <> 'pending' OR "
            "(approved_category_id IS NULL AND approved_department_id IS NULL "
            "AND approved_urgency IS NULL AND completed_at IS NULL)",
            name="ck_reviews_pending_consistency",
        ),
        CheckConstraint(
            "outcome NOT IN ('approved', 'corrected', 'rejected') "
            "OR completed_at IS NOT NULL",
            name="ck_reviews_completed_outcome_requires_completed_at",
        ),
        CheckConstraint(
            "outcome <> 'approved' OR "
            "(approved_category_id IS NOT NULL AND approved_department_id IS NOT NULL "
            "AND approved_urgency IS NOT NULL)",
            name="ck_reviews_approved_requires_routing",
        ),
        CheckConstraint(
            "outcome <> 'corrected' OR "
            "(approved_category_id IS NOT NULL AND approved_department_id IS NOT NULL "
            "AND approved_urgency IS NOT NULL)",
            name="ck_reviews_corrected_requires_routing",
        ),
        CheckConstraint(
            "outcome <> 'rejected' OR "
            "(approved_category_id IS NULL AND approved_department_id IS NULL "
            "AND approved_urgency IS NULL)",
            name="ck_reviews_rejected_has_no_routing",
        ),
        Index("uq_reviews_prediction_id", "prediction_id", unique=True),
        Index("ix_reviews_complaint_id", "complaint_id"),
        Index("ix_reviews_reviewer_id", "reviewer_id"),
        Index("ix_reviews_approved_category_id", "approved_category_id"),
        Index("ix_reviews_approved_department_id", "approved_department_id"),
        Index("ix_reviews_outcome_created_at", "outcome", "created_at"),
        Index("ix_reviews_reviewer_created_at", "reviewer_id", "created_at"),
    )

    complaint: Mapped[Complaint] = relationship(back_populates="reviews")
    prediction: Mapped[Prediction] = relationship(
        back_populates="review",
        uselist=False,
    )
    reviewer: Mapped[User] = relationship(back_populates="reviews_performed")
    approved_category: Mapped[ComplaintCategory | None] = relationship(
        back_populates="approved_reviews"
    )
    approved_department: Mapped[Department | None] = relationship(
        back_populates="approved_reviews"
    )
