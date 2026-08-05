"""Create deployment candidates.

Revision ID: 20260805_10
Revises: 20260805_09
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_10"
down_revision: str | None = "20260805_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status = postgresql.ENUM("candidate", "staged", "active", "retired", "rejected", name="deployment_candidate_status", create_type=False)


def upgrade() -> None:
    _status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "deployment_candidates",
        sa.Column("model_promotion_decision_id", sa.Uuid(), nullable=False),
        sa.Column("benchmark_result_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", _status, server_default="candidate", nullable=False),
        sa.Column("registered_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retirement_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("retirement_reason IS NULL OR btrim(retirement_reason) <> ''", name="ck_deployment_candidates_retirement_reason_not_blank"),
        sa.CheckConstraint("notes IS NULL OR btrim(notes) <> ''", name="ck_deployment_candidates_notes_not_blank"),
        sa.CheckConstraint("status <> 'candidate' OR (staged_at IS NULL AND activated_at IS NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_candidate_consistency"),
        sa.CheckConstraint("status <> 'staged' OR (staged_at IS NOT NULL AND activated_at IS NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_staged_consistency"),
        sa.CheckConstraint("status <> 'active' OR (staged_at IS NOT NULL AND activated_at IS NOT NULL AND retired_at IS NULL AND retirement_reason IS NULL)", name="ck_deployment_candidates_active_consistency"),
        sa.CheckConstraint("status <> 'retired' OR (retired_at IS NOT NULL AND retirement_reason IS NOT NULL)", name="ck_deployment_candidates_retired_consistency"),
        sa.CheckConstraint("status <> 'rejected' OR (retired_at IS NOT NULL AND retirement_reason IS NOT NULL AND activated_at IS NULL)", name="ck_deployment_candidates_rejected_consistency"),
        sa.CheckConstraint("staged_at IS NULL OR staged_at >= registered_at", name="ck_deployment_candidates_staged_at_order"),
        sa.CheckConstraint("activated_at IS NULL OR (activated_at >= registered_at AND (staged_at IS NULL OR activated_at >= staged_at))", name="ck_deployment_candidates_activated_at_order"),
        sa.CheckConstraint("retired_at IS NULL OR (retired_at >= registered_at AND (activated_at IS NULL OR retired_at >= activated_at))", name="ck_deployment_candidates_retired_at_order"),
        sa.ForeignKeyConstraint(["model_promotion_decision_id"], ["model_promotion_decisions.id"], name="fk_deployment_candidates_promotion_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["benchmark_result_id"], ["benchmark_results.id"], name="fk_deployment_candidates_result_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], name="fk_deployment_candidates_model_version_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"], name="fk_deployment_candidates_registered_by_user_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns, unique in (
        ("uq_deployment_candidates_promotion_id", ["model_promotion_decision_id"], True),
        ("ix_deployment_candidates_result_id", ["benchmark_result_id"], False),
        ("ix_deployment_candidates_model_version_id", ["model_version_id"], False),
        ("ix_deployment_candidates_status", ["status"], False),
        ("ix_deployment_candidates_registered_by_user_id", ["registered_by_user_id"], False),
        ("ix_deployment_candidates_registered_at", ["registered_at"], False),
        ("ix_deployment_candidates_staged_at", ["staged_at"], False),
        ("ix_deployment_candidates_activated_at", ["activated_at"], False),
        ("ix_deployment_candidates_retired_at", ["retired_at"], False),
    ):
        op.create_index(name, "deployment_candidates", columns, unique=unique)
    op.create_index("uq_deployment_candidates_single_active", "deployment_candidates", ["status"], unique=True, postgresql_where=sa.text("status = 'active'"))


def downgrade() -> None:
    for name in (
        "uq_deployment_candidates_single_active", "ix_deployment_candidates_retired_at",
        "ix_deployment_candidates_activated_at", "ix_deployment_candidates_staged_at",
        "ix_deployment_candidates_registered_at", "ix_deployment_candidates_registered_by_user_id",
        "ix_deployment_candidates_status", "ix_deployment_candidates_model_version_id",
        "ix_deployment_candidates_result_id", "uq_deployment_candidates_promotion_id",
    ):
        op.drop_index(name, table_name="deployment_candidates")
    op.drop_table("deployment_candidates")
    _status.drop(op.get_bind(), checkfirst=True)
