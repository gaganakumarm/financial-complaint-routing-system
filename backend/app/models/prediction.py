"""Immutable AI prediction evidence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.complaint import ComplaintUrgency, complaint_urgency_enum

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.complaint_category import ComplaintCategory
    from app.models.department import Department
    from app.models.model_version import ModelVersion


class Prediction(UUIDPrimaryKeyMixin, Base):
    """Immutable historical evidence preserving an AI model's output."""

    __tablename__ = "predictions"

    complaint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "complaints.id",
            name="fk_predictions_complaint_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "model_versions.id",
            name="fk_predictions_model_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    predicted_category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "complaint_categories.id",
            name="fk_predictions_predicted_category_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    predicted_department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "departments.id",
            name="fk_predictions_predicted_department_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    predicted_urgency: Mapped[ComplaintUrgency | None] = mapped_column(
        complaint_urgency_enum(),
        nullable=True,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 5),
        nullable=True,
    )
    raw_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    inference_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_predictions_confidence_score_range",
        ),
        CheckConstraint(
            "failure_code IS NULL OR btrim(failure_code) <> ''",
            name="ck_predictions_failure_code_not_blank",
        ),
        CheckConstraint(
            "inference_latency_ms IS NULL OR inference_latency_ms >= 0",
            name="ck_predictions_inference_latency_non_negative",
        ),
        CheckConstraint(
            "NOT output_valid OR "
            "(failure_code IS NULL AND failure_message IS NULL)",
            name="ck_predictions_failure_consistency",
        ),
        Index("ix_predictions_complaint_id", "complaint_id"),
        Index("ix_predictions_model_version_id", "model_version_id"),
        Index("ix_predictions_predicted_category_id", "predicted_category_id"),
        Index("ix_predictions_predicted_department_id", "predicted_department_id"),
        Index("ix_predictions_complaint_created_at", "complaint_id", "created_at"),
        Index(
            "ix_predictions_model_version_created_at",
            "model_version_id",
            "created_at",
        ),
    )

    complaint: Mapped[Complaint] = relationship(back_populates="predictions")
    model_version: Mapped[ModelVersion] = relationship(back_populates="predictions")
    predicted_category: Mapped[ComplaintCategory | None] = relationship(
        back_populates="predictions"
    )
    predicted_department: Mapped[Department | None] = relationship(
        back_populates="predictions"
    )
