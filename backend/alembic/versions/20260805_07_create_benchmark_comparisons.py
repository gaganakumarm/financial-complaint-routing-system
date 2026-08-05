"""Create benchmark comparisons.

Revision ID: 20260805_07
Revises: 20260805_06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_07"
down_revision: str | None = "20260805_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmark_comparisons",
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_checksum", sa.String(length=128), nullable=False),
        sa.Column("dataset_example_count", sa.Integer(), nullable=False),
        sa.Column("winner_experiment_id", sa.Uuid(), nullable=False),
        sa.Column("ranking_metric", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(dataset_checksum) <> ''", name="ck_benchmark_comparisons_dataset_checksum_not_blank"),
        sa.CheckConstraint("dataset_example_count > 0", name="ck_benchmark_comparisons_example_count_positive"),
        sa.CheckConstraint("btrim(ranking_metric) <> ''", name="ck_benchmark_comparisons_ranking_metric_not_blank"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], name="fk_benchmark_comparisons_dataset_version_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["winner_experiment_id"], ["benchmark_experiments.id"], name="fk_benchmark_comparisons_winner_experiment_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_benchmark_comparisons_created_by_user_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_comparisons_dataset_version_id", "benchmark_comparisons", ["dataset_version_id"])
    op.create_index("ix_benchmark_comparisons_winner_experiment_id", "benchmark_comparisons", ["winner_experiment_id"])
    op.create_index("ix_benchmark_comparisons_created_by_user_id", "benchmark_comparisons", ["created_by_user_id"])
    op.create_index("ix_benchmark_comparisons_created_at", "benchmark_comparisons", ["created_at"])

    op.create_table(
        "benchmark_comparison_members",
        sa.Column("benchmark_comparison_id", sa.Uuid(), nullable=False),
        sa.Column("benchmark_experiment_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_benchmark_comparison_members_rank_positive"),
        sa.ForeignKeyConstraint(["benchmark_comparison_id"], ["benchmark_comparisons.id"], name="fk_benchmark_comparison_members_comparison_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benchmark_experiment_id"], ["benchmark_experiments.id"], name="fk_benchmark_comparison_members_experiment_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_benchmark_comparison_members_comparison_experiment", "benchmark_comparison_members", ["benchmark_comparison_id", "benchmark_experiment_id"], unique=True)
    op.create_index("uq_benchmark_comparison_members_comparison_rank", "benchmark_comparison_members", ["benchmark_comparison_id", "rank"], unique=True)
    op.create_index("ix_benchmark_comparison_members_comparison_id", "benchmark_comparison_members", ["benchmark_comparison_id"])
    op.create_index("ix_benchmark_comparison_members_experiment_id", "benchmark_comparison_members", ["benchmark_experiment_id"])
    op.create_index("ix_benchmark_comparison_members_rank", "benchmark_comparison_members", ["rank"])


def downgrade() -> None:
    op.drop_index("ix_benchmark_comparison_members_rank", table_name="benchmark_comparison_members")
    op.drop_index("ix_benchmark_comparison_members_experiment_id", table_name="benchmark_comparison_members")
    op.drop_index("ix_benchmark_comparison_members_comparison_id", table_name="benchmark_comparison_members")
    op.drop_index("uq_benchmark_comparison_members_comparison_rank", table_name="benchmark_comparison_members")
    op.drop_index("uq_benchmark_comparison_members_comparison_experiment", table_name="benchmark_comparison_members")
    op.drop_table("benchmark_comparison_members")
    op.drop_index("ix_benchmark_comparisons_created_at", table_name="benchmark_comparisons")
    op.drop_index("ix_benchmark_comparisons_created_by_user_id", table_name="benchmark_comparisons")
    op.drop_index("ix_benchmark_comparisons_winner_experiment_id", table_name="benchmark_comparisons")
    op.drop_index("ix_benchmark_comparisons_dataset_version_id", table_name="benchmark_comparisons")
    op.drop_table("benchmark_comparisons")
