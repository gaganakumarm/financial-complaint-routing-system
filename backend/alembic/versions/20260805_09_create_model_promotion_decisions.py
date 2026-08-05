"""Create model promotion decisions.

Revision ID: 20260805_09
Revises: 20260805_08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260805_09"
down_revision: str | None = "20260805_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status = postgresql.ENUM(
    "pending", "approved", "rejected", "cancelled",
    name="model_promotion_status", create_type=False,
)


def upgrade() -> None:
    _status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "model_promotion_decisions",
        sa.Column("benchmark_comparison_id", sa.Uuid(), nullable=False),
        sa.Column("selected_benchmark_result_id", sa.Uuid(), nullable=False),
        sa.Column("selected_model_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", _status, server_default="pending", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("override_winner", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(rationale) <> ''", name="ck_model_promotion_decisions_rationale_not_blank"),
        sa.CheckConstraint("review_note IS NULL OR btrim(review_note) <> ''", name="ck_model_promotion_decisions_review_note_not_blank"),
        sa.CheckConstraint("status <> 'pending' OR (reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND review_note IS NULL)", name="ck_model_promotion_decisions_pending_review_fields_absent"),
        sa.CheckConstraint("status NOT IN ('approved', 'rejected', 'cancelled') OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)", name="ck_model_promotion_decisions_terminal_review_fields_present"),
        sa.CheckConstraint("reviewed_at IS NULL OR reviewed_at >= requested_at", name="ck_model_promotion_decisions_review_timestamps_order"),
        sa.ForeignKeyConstraint(["benchmark_comparison_id"], ["benchmark_comparisons.id"], name="fk_model_promotion_decisions_comparison_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["selected_benchmark_result_id"], ["benchmark_results.id"], name="fk_model_promotion_decisions_result_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["selected_model_version_id"], ["model_versions.id"], name="fk_model_promotion_decisions_model_version_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name="fk_model_promotion_decisions_requested_by_user_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name="fk_model_promotion_decisions_reviewed_by_user_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_model_promotion_decisions_comparison_id", ["benchmark_comparison_id"]),
        ("ix_model_promotion_decisions_result_id", ["selected_benchmark_result_id"]),
        ("ix_model_promotion_decisions_model_version_id", ["selected_model_version_id"]),
        ("ix_model_promotion_decisions_status", ["status"]),
        ("ix_model_promotion_decisions_requested_by_user_id", ["requested_by_user_id"]),
        ("ix_model_promotion_decisions_reviewed_by_user_id", ["reviewed_by_user_id"]),
        ("ix_model_promotion_decisions_requested_at", ["requested_at"]),
        ("ix_model_promotion_decisions_reviewed_at", ["reviewed_at"]),
    ):
        op.create_index(name, "model_promotion_decisions", columns)
    op.create_index(
        "uq_model_promotion_decisions_pending_comparison",
        "model_promotion_decisions",
        ["benchmark_comparison_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    for name in (
        "uq_model_promotion_decisions_pending_comparison",
        "ix_model_promotion_decisions_reviewed_at",
        "ix_model_promotion_decisions_requested_at",
        "ix_model_promotion_decisions_reviewed_by_user_id",
        "ix_model_promotion_decisions_requested_by_user_id",
        "ix_model_promotion_decisions_status",
        "ix_model_promotion_decisions_model_version_id",
        "ix_model_promotion_decisions_result_id",
        "ix_model_promotion_decisions_comparison_id",
    ):
        op.drop_index(name, table_name="model_promotion_decisions")
    op.drop_table("model_promotion_decisions")
    _status.drop(op.get_bind(), checkfirst=True)
