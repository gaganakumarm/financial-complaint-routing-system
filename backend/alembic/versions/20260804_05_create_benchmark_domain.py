"""Create benchmark domain.

Revision ID: 20260804_05
Revises: 20260804_04
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_05"
down_revision: str | None = "20260804_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_dataset_split = postgresql.ENUM(
    "train", "validation", "test", "full", name="dataset_split", create_type=False
)
_experiment_status = postgresql.ENUM(
    "pending", "running", "completed", "failed", "cancelled",
    name="benchmark_experiment_status", create_type=False,
)


def upgrade() -> None:
    """Create dataset versioning and benchmark persistence."""
    bind = op.get_bind()
    _dataset_split.create(bind, checkfirst=False)
    _experiment_status.create(bind, checkfirst=False)

    op.create_table(
        "dataset_versions",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("taxonomy_version", sa.String(length=50), nullable=False),
        sa.Column("split", _dataset_split, nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("preparation_details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_dataset_versions_name_not_blank"),
        sa.CheckConstraint("btrim(version) <> ''", name="ck_dataset_versions_version_not_blank"),
        sa.CheckConstraint("btrim(source_name) <> ''", name="ck_dataset_versions_source_name_not_blank"),
        sa.CheckConstraint("btrim(taxonomy_version) <> ''", name="ck_dataset_versions_taxonomy_version_not_blank"),
        sa.CheckConstraint("btrim(content_hash) <> ''", name="ck_dataset_versions_content_hash_not_blank"),
        sa.CheckConstraint("record_count > 0", name="ck_dataset_versions_record_count_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_dataset_versions_name_version_split", "dataset_versions", ["name", "version", "split"], unique=True)
    op.create_index("uq_dataset_versions_content_hash", "dataset_versions", ["content_hash"], unique=True)
    op.create_index("ix_dataset_versions_split", "dataset_versions", ["split"], unique=False)
    op.create_index("ix_dataset_versions_taxonomy_version", "dataset_versions", ["taxonomy_version"], unique=False)

    op.create_table(
        "benchmark_experiments",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", _experiment_status, server_default="pending", nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_benchmark_experiments_name_not_blank"),
        sa.CheckConstraint("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name="ck_benchmark_experiments_timestamps_order"),
        sa.CheckConstraint("status <> 'pending' OR (started_at IS NULL AND completed_at IS NULL AND failure_message IS NULL)", name="ck_benchmark_experiments_pending_consistency"),
        sa.CheckConstraint("status <> 'running' OR (started_at IS NOT NULL AND completed_at IS NULL AND failure_message IS NULL)", name="ck_benchmark_experiments_running_requires_started_at"),
        sa.CheckConstraint("status <> 'completed' OR (started_at IS NOT NULL AND completed_at IS NOT NULL AND failure_message IS NULL)", name="ck_benchmark_experiments_completed_requires_timestamps"),
        sa.CheckConstraint("status <> 'failed' OR (started_at IS NOT NULL AND completed_at IS NOT NULL)", name="ck_benchmark_experiments_failed_requires_completion"),
        sa.CheckConstraint("(status = 'failed' OR failure_message IS NULL) AND (failure_message IS NULL OR btrim(failure_message) <> '')", name="ck_benchmark_experiments_failure_message_consistency"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], name="fk_benchmark_experiments_dataset_version_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_experiments_dataset_version_id", "benchmark_experiments", ["dataset_version_id"], unique=False)
    op.create_index("ix_benchmark_experiments_status", "benchmark_experiments", ["status"], unique=False)
    op.create_index("ix_benchmark_experiments_status_created_at", "benchmark_experiments", ["status", "created_at"], unique=False)

    op.create_table(
        "benchmark_results",
        sa.Column("benchmark_experiment_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Numeric(6, 5), nullable=True),
        sa.Column("macro_precision", sa.Numeric(6, 5), nullable=True),
        sa.Column("macro_recall", sa.Numeric(6, 5), nullable=True),
        sa.Column("macro_f1", sa.Numeric(6, 5), nullable=True),
        sa.Column("cost_weighted_error", sa.Numeric(14, 6), nullable=True),
        sa.Column("structured_output_validity_rate", sa.Numeric(6, 5), nullable=True),
        sa.Column("average_inference_latency_ms", sa.Numeric(14, 4), nullable=True),
        sa.Column("throughput_per_second", sa.Numeric(14, 4), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(16, 6), nullable=True),
        sa.Column("per_class_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("additional_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("sample_count > 0", name="ck_benchmark_results_sample_count_positive"),
        sa.CheckConstraint("accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)", name="ck_benchmark_results_accuracy_range"),
        sa.CheckConstraint("macro_precision IS NULL OR (macro_precision >= 0 AND macro_precision <= 1)", name="ck_benchmark_results_macro_precision_range"),
        sa.CheckConstraint("macro_recall IS NULL OR (macro_recall >= 0 AND macro_recall <= 1)", name="ck_benchmark_results_macro_recall_range"),
        sa.CheckConstraint("macro_f1 IS NULL OR (macro_f1 >= 0 AND macro_f1 <= 1)", name="ck_benchmark_results_macro_f1_range"),
        sa.CheckConstraint("structured_output_validity_rate IS NULL OR (structured_output_validity_rate >= 0 AND structured_output_validity_rate <= 1)", name="ck_benchmark_results_validity_rate_range"),
        sa.CheckConstraint("cost_weighted_error IS NULL OR cost_weighted_error >= 0", name="ck_benchmark_results_cost_weighted_error_non_negative"),
        sa.CheckConstraint("average_inference_latency_ms IS NULL OR average_inference_latency_ms >= 0", name="ck_benchmark_results_latency_non_negative"),
        sa.CheckConstraint("throughput_per_second IS NULL OR throughput_per_second >= 0", name="ck_benchmark_results_throughput_non_negative"),
        sa.CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="ck_benchmark_results_estimated_cost_non_negative"),
        sa.ForeignKeyConstraint(["benchmark_experiment_id"], ["benchmark_experiments.id"], name="fk_benchmark_results_experiment_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], name="fk_benchmark_results_model_version_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_benchmark_results_experiment_model", "benchmark_results", ["benchmark_experiment_id", "model_version_id"], unique=True)
    op.create_index("ix_benchmark_results_experiment_id", "benchmark_results", ["benchmark_experiment_id"], unique=False)
    op.create_index("ix_benchmark_results_model_version_id", "benchmark_results", ["model_version_id"], unique=False)
    op.create_index("ix_benchmark_results_model_created_at", "benchmark_results", ["model_version_id", "created_at"], unique=False)


def downgrade() -> None:
    """Drop benchmark persistence in dependency-safe reverse order."""
    op.drop_index("ix_benchmark_results_model_created_at", table_name="benchmark_results")
    op.drop_index("ix_benchmark_results_model_version_id", table_name="benchmark_results")
    op.drop_index("ix_benchmark_results_experiment_id", table_name="benchmark_results")
    op.drop_index("uq_benchmark_results_experiment_model", table_name="benchmark_results")
    op.drop_table("benchmark_results")
    op.drop_index("ix_benchmark_experiments_status_created_at", table_name="benchmark_experiments")
    op.drop_index("ix_benchmark_experiments_status", table_name="benchmark_experiments")
    op.drop_index("ix_benchmark_experiments_dataset_version_id", table_name="benchmark_experiments")
    op.drop_table("benchmark_experiments")
    op.drop_index("ix_dataset_versions_taxonomy_version", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_split", table_name="dataset_versions")
    op.drop_index("uq_dataset_versions_content_hash", table_name="dataset_versions")
    op.drop_index("uq_dataset_versions_name_version_split", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    bind = op.get_bind()
    _experiment_status.drop(bind, checkfirst=False)
    _dataset_split.drop(bind, checkfirst=False)
