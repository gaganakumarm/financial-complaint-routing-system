"""AI model registry model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.prediction import Prediction


class ModelType(StrEnum):
    """Registered model implementation types persisted as lowercase values."""

    TFIDF_CLASSIFIER = "tfidf_classifier"
    EMBEDDING_CLASSIFIER = "embedding_classifier"
    PROMPTED_LLM = "prompted_llm"
    FINE_TUNED_LLM = "fine_tuned_llm"
    HYBRID = "hybrid"


def model_type_enum() -> Enum:
    """Build the native model-type enum mapping."""
    return Enum(
        ModelType,
        name="model_type",
        values_callable=lambda members: [member.value for member in members],
    )


class ModelVersion(UUIDPrimaryKeyMixin, Base):
    """Metadata and lifecycle state for a registered AI model version."""

    __tablename__ = "model_versions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_type: Mapped[ModelType] = mapped_column(model_type_enum(), nullable=False)
    base_model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    artifact_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_model_versions_name_not_blank"),
        CheckConstraint(
            "btrim(version) <> ''",
            name="ck_model_versions_version_not_blank",
        ),
        CheckConstraint(
            "NOT is_active OR is_approved",
            name="ck_model_versions_active_requires_approval",
        ),
        CheckConstraint(
            "NOT is_active OR activated_at IS NOT NULL",
            name="ck_model_versions_active_requires_activated_at",
        ),
        CheckConstraint(
            "deactivated_at IS NULL OR activated_at IS NULL "
            "OR deactivated_at >= activated_at",
            name="ck_model_versions_activation_timestamps_order",
        ),
        Index("uq_model_versions_name_version", "name", "version", unique=True),
        Index("ix_model_versions_model_type", "model_type"),
        Index("ix_model_versions_is_active", "is_active"),
        Index(
            "uq_model_versions_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="model_version"
    )
