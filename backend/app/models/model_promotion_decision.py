"""Auditable persistence for model-promotion decisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, Uuid, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_comparison import BenchmarkComparison
    from app.models.benchmark_result import BenchmarkResult
    from app.models.model_version import ModelVersion
    from app.models.user import User


class ModelPromotionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def model_promotion_status_enum() -> Enum:
    return Enum(
        ModelPromotionStatus,
        name="model_promotion_status",
        values_callable=lambda members: [member.value for member in members],
    )


class ModelPromotionDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_promotion_decisions"

    benchmark_comparison_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("benchmark_comparisons.id", name="fk_model_promotion_decisions_comparison_id", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_benchmark_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("benchmark_results.id", name="fk_model_promotion_decisions_result_id", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("model_versions.id", name="fk_model_promotion_decisions_model_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ModelPromotionStatus] = mapped_column(
        model_promotion_status_enum(),
        default=ModelPromotionStatus.PENDING,
        server_default=ModelPromotionStatus.PENDING.value,
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    override_winner: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_model_promotion_decisions_requested_by_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_model_promotion_decisions_reviewed_by_user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("btrim(rationale) <> ''", name="ck_model_promotion_decisions_rationale_not_blank"),
        CheckConstraint("review_note IS NULL OR btrim(review_note) <> ''", name="ck_model_promotion_decisions_review_note_not_blank"),
        CheckConstraint("status <> 'pending' OR (reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND review_note IS NULL)", name="ck_model_promotion_decisions_pending_review_fields_absent"),
        CheckConstraint("status NOT IN ('approved', 'rejected', 'cancelled') OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)", name="ck_model_promotion_decisions_terminal_review_fields_present"),
        CheckConstraint("reviewed_at IS NULL OR reviewed_at >= requested_at", name="ck_model_promotion_decisions_review_timestamps_order"),
        Index("ix_model_promotion_decisions_comparison_id", "benchmark_comparison_id"),
        Index("ix_model_promotion_decisions_result_id", "selected_benchmark_result_id"),
        Index("ix_model_promotion_decisions_model_version_id", "selected_model_version_id"),
        Index("ix_model_promotion_decisions_status", "status"),
        Index("ix_model_promotion_decisions_requested_by_user_id", "requested_by_user_id"),
        Index("ix_model_promotion_decisions_reviewed_by_user_id", "reviewed_by_user_id"),
        Index("ix_model_promotion_decisions_requested_at", "requested_at"),
        Index("ix_model_promotion_decisions_reviewed_at", "reviewed_at"),
        Index("uq_model_promotion_decisions_pending_comparison", "benchmark_comparison_id", unique=True, postgresql_where=text("status = 'pending'")),
    )

    benchmark_comparison: Mapped[BenchmarkComparison] = relationship(back_populates="model_promotion_decisions")
    selected_benchmark_result: Mapped[BenchmarkResult] = relationship(back_populates="model_promotion_decisions")
    selected_model_version: Mapped[ModelVersion] = relationship(back_populates="model_promotion_decisions")
    requested_by_user: Mapped[User] = relationship(back_populates="requested_model_promotions", foreign_keys=[requested_by_user_id])
    reviewed_by_user: Mapped[User | None] = relationship(back_populates="reviewed_model_promotions", foreign_keys=[reviewed_by_user_id])
