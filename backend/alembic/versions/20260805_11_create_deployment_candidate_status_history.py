"""Create deployment candidate status history.

Revision ID: 20260805_11
Revises: 20260805_10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_11"
down_revision: str | None = "20260805_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status = postgresql.ENUM(
    "candidate", "staged", "active", "retired", "rejected",
    name="deployment_candidate_status", create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "deployment_candidate_status_history",
        sa.Column("deployment_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", _status, nullable=True),
        sa.Column("new_status", _status, nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_deployment_candidate_status_history_note_not_blank"),
        sa.CheckConstraint("previous_status IS NULL OR previous_status <> new_status", name="ck_deployment_candidate_status_history_status_changed"),
        sa.CheckConstraint("previous_status IS NOT NULL OR new_status = 'candidate'", name="ck_deployment_candidate_status_history_initial_registration"),
        sa.CheckConstraint("new_status = 'candidate' OR previous_status IS NOT NULL", name="ck_deployment_candidate_status_history_previous_status_required"),
        sa.ForeignKeyConstraint(["deployment_candidate_id"], ["deployment_candidates.id"], name="fk_deployment_candidate_status_history_candidate_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], name="fk_deployment_candidate_status_history_changed_by_user_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_deployment_candidate_status_history_candidate_chronology", ["deployment_candidate_id", "changed_at", "id"]),
        ("ix_deployment_candidate_status_history_changed_by_user_id", ["changed_by_user_id"]),
        ("ix_deployment_candidate_status_history_new_status", ["new_status"]),
        ("ix_deployment_candidate_status_history_changed_at", ["changed_at"]),
    ):
        op.create_index(name, "deployment_candidate_status_history", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_deployment_candidate_status_history_changed_at",
        "ix_deployment_candidate_status_history_new_status",
        "ix_deployment_candidate_status_history_changed_by_user_id",
        "ix_deployment_candidate_status_history_candidate_chronology",
    ):
        op.drop_index(name, table_name="deployment_candidate_status_history")
    op.drop_table("deployment_candidate_status_history")
