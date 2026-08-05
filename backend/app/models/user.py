"""User model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.benchmark_comparison import BenchmarkComparison
    from app.models.complaint import Complaint
    from app.models.complaint_status_history import ComplaintStatusHistory
    from app.models.role import Role
    from app.models.review import Review
    from app.models.model_promotion_decision import ModelPromotionDecision
    from app.models.deployment_candidate import DeploymentCandidate


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An application user associated with exactly one role."""

    __tablename__ = "users"

    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "roles.id",
            name="fk_users_role_id_roles",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("btrim(email) <> ''", name="ck_users_email_not_blank"),
        CheckConstraint(
            "btrim(password_hash) <> ''",
            name="ck_users_password_hash_not_blank",
        ),
        CheckConstraint(
            "btrim(full_name) <> ''",
            name="ck_users_full_name_not_blank",
        ),
        Index("ix_users_role_id", "role_id"),
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )

    role: Mapped[Role] = relationship(back_populates="users")
    submitted_complaints: Mapped[list[Complaint]] = relationship(
        back_populates="customer",
        foreign_keys="Complaint.customer_id",
    )
    complaint_status_changes: Mapped[list[ComplaintStatusHistory]] = relationship(
        back_populates="changed_by_user",
        foreign_keys="ComplaintStatusHistory.changed_by_user_id",
    )
    reviews_performed: Mapped[list[Review]] = relationship(back_populates="reviewer")
    created_benchmark_comparisons: Mapped[list[BenchmarkComparison]] = relationship(back_populates="created_by_user", foreign_keys="BenchmarkComparison.created_by_user_id")
    requested_model_promotions: Mapped[list[ModelPromotionDecision]] = relationship(back_populates="requested_by_user", foreign_keys="ModelPromotionDecision.requested_by_user_id")
    reviewed_model_promotions: Mapped[list[ModelPromotionDecision]] = relationship(back_populates="reviewed_by_user", foreign_keys="ModelPromotionDecision.reviewed_by_user_id")
    registered_deployment_candidates: Mapped[list[DeploymentCandidate]] = relationship(back_populates="registered_by_user", foreign_keys="DeploymentCandidate.registered_by_user_id")
