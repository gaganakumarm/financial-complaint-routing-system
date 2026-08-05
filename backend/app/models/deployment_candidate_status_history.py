"""Append-only deployment-candidate lifecycle history."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.deployment_candidate import (
    DeploymentCandidateStatus,
    deployment_candidate_status_enum,
)

if TYPE_CHECKING:
    from app.models.deployment_candidate import DeploymentCandidate
    from app.models.user import User


class DeploymentCandidateStatusHistory(UUIDPrimaryKeyMixin, Base):
    """An immutable record of a deployment-candidate status transition."""

    __tablename__ = "deployment_candidate_status_history"

    deployment_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "deployment_candidates.id",
            name="fk_deployment_candidate_status_history_candidate_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    previous_status: Mapped[DeploymentCandidateStatus | None] = mapped_column(
        deployment_candidate_status_enum(), nullable=True
    )
    new_status: Mapped[DeploymentCandidateStatus] = mapped_column(
        deployment_candidate_status_enum(), nullable=False
    )
    changed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_deployment_candidate_status_history_changed_by_user_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "note IS NULL OR btrim(note) <> ''",
            name="ck_deployment_candidate_status_history_note_not_blank",
        ),
        CheckConstraint(
            "previous_status IS NULL OR previous_status <> new_status",
            name="ck_deployment_candidate_status_history_status_changed",
        ),
        CheckConstraint(
            "previous_status IS NOT NULL OR new_status = 'candidate'",
            name="ck_deployment_candidate_status_history_initial_registration",
        ),
        CheckConstraint(
            "new_status = 'candidate' OR previous_status IS NOT NULL",
            name="ck_deployment_candidate_status_history_previous_status_required",
        ),
        Index(
            "ix_deployment_candidate_status_history_candidate_chronology",
            "deployment_candidate_id",
            "changed_at",
            "id",
        ),
        Index(
            "ix_deployment_candidate_status_history_changed_by_user_id",
            "changed_by_user_id",
        ),
        Index("ix_deployment_candidate_status_history_new_status", "new_status"),
        Index("ix_deployment_candidate_status_history_changed_at", "changed_at"),
    )

    deployment_candidate: Mapped[DeploymentCandidate] = relationship(
        back_populates="status_history"
    )
    changed_by_user: Mapped[User] = relationship(
        back_populates="deployment_candidate_status_changes",
        foreign_keys=[changed_by_user_id],
    )


__all__ = ["DeploymentCandidateStatusHistory"]
