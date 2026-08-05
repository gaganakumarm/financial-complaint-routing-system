"""Deployment-candidate metadata without deployment execution."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_result import BenchmarkResult
    from app.models.model_promotion_decision import ModelPromotionDecision
    from app.models.model_version import ModelVersion
    from app.models.user import User
    from app.models.deployment_candidate_status_history import DeploymentCandidateStatusHistory


class DeploymentCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    STAGED = "staged"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"


def deployment_candidate_status_enum() -> Enum:
    return Enum(
        DeploymentCandidateStatus,
        name="deployment_candidate_status",
        values_callable=lambda members: [member.value for member in members],
    )


class DeploymentCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployment_candidates"

    model_promotion_decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_promotion_decisions.id", name="fk_deployment_candidates_promotion_id", ondelete="RESTRICT"), nullable=False
    )
    benchmark_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("benchmark_results.id", name="fk_deployment_candidates_result_id", ondelete="RESTRICT"), nullable=False
    )
    model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_versions.id", name="fk_deployment_candidates_model_version_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[DeploymentCandidateStatus] = mapped_column(
        deployment_candidate_status_enum(), default=DeploymentCandidateStatus.CANDIDATE,
        server_default=DeploymentCandidateStatus.CANDIDATE.value, nullable=False,
    )
    registered_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", name="fk_deployment_candidates_registered_by_user_id", ondelete="RESTRICT"), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    staged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("retirement_reason IS NULL OR btrim(retirement_reason) <> ''", name="ck_deployment_candidates_retirement_reason_not_blank"),
        CheckConstraint("notes IS NULL OR btrim(notes) <> ''", name="ck_deployment_candidates_notes_not_blank"),
        CheckConstraint("status <> 'candidate' OR (staged_at IS NULL AND activated_at IS NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_candidate_consistency"),
        CheckConstraint("status <> 'staged' OR (staged_at IS NOT NULL AND activated_at IS NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_staged_consistency"),
        CheckConstraint("status <> 'active' OR (staged_at IS NOT NULL AND activated_at IS NOT NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_active_consistency"),
        CheckConstraint("status <> 'retired' OR (retired_at IS NOT NULL AND retirement_reason IS NOT NULL)", name="ck_deployment_candidates_retired_consistency"),
        CheckConstraint("status <> 'rejected' OR (retired_at IS NOT NULL AND retirement_reason IS NOT NULL AND activated_at IS NULL)", name="ck_deployment_candidates_rejected_consistency"),
        CheckConstraint("staged_at IS NULL OR staged_at >= registered_at", name="ck_deployment_candidates_staged_at_order"),
        CheckConstraint("activated_at IS NULL OR (activated_at >= registered_at AND (staged_at IS NULL OR activated_at >= staged_at))", name="ck_deployment_candidates_activated_at_order"),
        CheckConstraint("retired_at IS NULL OR (retired_at >= registered_at AND (activated_at IS NULL OR retired_at >= activated_at))", name="ck_deployment_candidates_retired_at_order"),
        Index("uq_deployment_candidates_promotion_id", "model_promotion_decision_id", unique=True),
        Index("ix_deployment_candidates_result_id", "benchmark_result_id"),
        Index("ix_deployment_candidates_model_version_id", "model_version_id"),
        Index("ix_deployment_candidates_status", "status"),
        Index("ix_deployment_candidates_registered_by_user_id", "registered_by_user_id"),
        Index("ix_deployment_candidates_registered_at", "registered_at"),
        Index("ix_deployment_candidates_staged_at", "staged_at"),
        Index("ix_deployment_candidates_activated_at", "activated_at"),
        Index("ix_deployment_candidates_retired_at", "retired_at"),
        Index("uq_deployment_candidates_single_active", "status", unique=True, postgresql_where=text("status = 'active'")),
    )

    model_promotion_decision: Mapped[ModelPromotionDecision] = relationship(back_populates="deployment_candidate")
    benchmark_result: Mapped[BenchmarkResult] = relationship(back_populates="deployment_candidates")
    model_version: Mapped[ModelVersion] = relationship(back_populates="deployment_candidates")
    registered_by_user: Mapped[User] = relationship(back_populates="registered_deployment_candidates", foreign_keys=[registered_by_user_id])
    status_history: Mapped[list[DeploymentCandidateStatusHistory]] = relationship(
        back_populates="deployment_candidate",
        order_by=(
            "DeploymentCandidateStatusHistory.changed_at.asc(), "
            "DeploymentCandidateStatusHistory.id.asc()"
        ),
    )
