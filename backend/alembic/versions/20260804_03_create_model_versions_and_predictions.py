"""Create model versions and predictions.

Revision ID: 20260804_03
Revises: 20260804_02
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_03"
down_revision: str | None = "20260804_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_model_type = postgresql.ENUM(
    "tfidf_classifier",
    "embedding_classifier",
    "prompted_llm",
    "fine_tuned_llm",
    "hybrid",
    name="model_type",
    create_type=False,
)
_complaint_urgency = postgresql.ENUM(
    "low",
    "medium",
    "high",
    "critical",
    name="complaint_urgency",
    create_type=False,
)


def upgrade() -> None:
    """Create the model registry and immutable prediction evidence tables."""
    _model_type.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "model_versions",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("model_type", _model_type, nullable=False),
        sa.Column("base_model_name", sa.String(length=200), nullable=True),
        sa.Column("artifact_location", sa.Text(), nullable=True),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_approved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "btrim(name) <> ''",
            name="ck_model_versions_name_not_blank",
        ),
        sa.CheckConstraint(
            "btrim(version) <> ''",
            name="ck_model_versions_version_not_blank",
        ),
        sa.CheckConstraint(
            "NOT is_active OR is_approved",
            name="ck_model_versions_active_requires_approval",
        ),
        sa.CheckConstraint(
            "NOT is_active OR activated_at IS NOT NULL",
            name="ck_model_versions_active_requires_activated_at",
        ),
        sa.CheckConstraint(
            "deactivated_at IS NULL OR activated_at IS NULL "
            "OR deactivated_at >= activated_at",
            name="ck_model_versions_activation_timestamps_order",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_model_versions_name_version",
        "model_versions",
        ["name", "version"],
        unique=True,
    )
    op.create_index(
        "ix_model_versions_model_type",
        "model_versions",
        ["model_type"],
        unique=False,
    )
    op.create_index(
        "ix_model_versions_is_active",
        "model_versions",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "uq_model_versions_single_active",
        "model_versions",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "predictions",
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("predicted_category_id", sa.Uuid(), nullable=True),
        sa.Column("predicted_department_id", sa.Uuid(), nullable=True),
        sa.Column("predicted_urgency", _complaint_urgency, nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("raw_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_valid", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("inference_latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_predictions_confidence_score_range",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR btrim(failure_code) <> ''",
            name="ck_predictions_failure_code_not_blank",
        ),
        sa.CheckConstraint(
            "inference_latency_ms IS NULL OR inference_latency_ms >= 0",
            name="ck_predictions_inference_latency_non_negative",
        ),
        sa.CheckConstraint(
            "NOT output_valid OR "
            "(failure_code IS NULL AND failure_message IS NULL)",
            name="ck_predictions_failure_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name="fk_predictions_complaint_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name="fk_predictions_model_version_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["predicted_category_id"],
            ["complaint_categories.id"],
            name="fk_predictions_predicted_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["predicted_department_id"],
            ["departments.id"],
            name="fk_predictions_predicted_department_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_predictions_complaint_id", "predictions", ["complaint_id"], unique=False
    )
    op.create_index(
        "ix_predictions_model_version_id",
        "predictions",
        ["model_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_predictions_predicted_category_id",
        "predictions",
        ["predicted_category_id"],
        unique=False,
    )
    op.create_index(
        "ix_predictions_predicted_department_id",
        "predictions",
        ["predicted_department_id"],
        unique=False,
    )
    op.create_index(
        "ix_predictions_complaint_created_at",
        "predictions",
        ["complaint_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_predictions_model_version_created_at",
        "predictions",
        ["model_version_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop prediction evidence before the model registry and its enum."""
    op.drop_index("ix_predictions_model_version_created_at", table_name="predictions")
    op.drop_index("ix_predictions_complaint_created_at", table_name="predictions")
    op.drop_index("ix_predictions_predicted_department_id", table_name="predictions")
    op.drop_index("ix_predictions_predicted_category_id", table_name="predictions")
    op.drop_index("ix_predictions_model_version_id", table_name="predictions")
    op.drop_index("ix_predictions_complaint_id", table_name="predictions")
    op.drop_table("predictions")

    op.drop_index("uq_model_versions_single_active", table_name="model_versions")
    op.drop_index("ix_model_versions_is_active", table_name="model_versions")
    op.drop_index("ix_model_versions_model_type", table_name="model_versions")
    op.drop_index("uq_model_versions_name_version", table_name="model_versions")
    op.drop_table("model_versions")

    _model_type.drop(op.get_bind(), checkfirst=False)
