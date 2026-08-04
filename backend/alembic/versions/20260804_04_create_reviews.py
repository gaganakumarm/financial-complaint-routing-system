"""Create reviews.

Revision ID: 20260804_04
Revises: 20260804_03
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_04"
down_revision: str | None = "20260804_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_review_outcome = postgresql.ENUM(
    "pending",
    "approved",
    "corrected",
    "rejected",
    name="review_outcome",
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
    """Create the review-outcome enum, reviews table, and indexes."""
    _review_outcome.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "reviews",
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("prediction_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "outcome",
            _review_outcome,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("approved_category_id", sa.Uuid(), nullable=True),
        sa.Column("approved_department_id", sa.Uuid(), nullable=True),
        sa.Column("approved_urgency", _complaint_urgency, nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_reviews_completion_timestamps_order",
        ),
        sa.CheckConstraint(
            "outcome <> 'pending' OR "
            "(approved_category_id IS NULL AND approved_department_id IS NULL "
            "AND approved_urgency IS NULL AND completed_at IS NULL)",
            name="ck_reviews_pending_consistency",
        ),
        sa.CheckConstraint(
            "outcome NOT IN ('approved', 'corrected', 'rejected') "
            "OR completed_at IS NOT NULL",
            name="ck_reviews_completed_outcome_requires_completed_at",
        ),
        sa.CheckConstraint(
            "outcome <> 'approved' OR "
            "(approved_category_id IS NOT NULL AND approved_department_id IS NOT NULL "
            "AND approved_urgency IS NOT NULL)",
            name="ck_reviews_approved_requires_routing",
        ),
        sa.CheckConstraint(
            "outcome <> 'corrected' OR "
            "(approved_category_id IS NOT NULL AND approved_department_id IS NOT NULL "
            "AND approved_urgency IS NOT NULL)",
            name="ck_reviews_corrected_requires_routing",
        ),
        sa.CheckConstraint(
            "outcome <> 'rejected' OR "
            "(approved_category_id IS NULL AND approved_department_id IS NULL "
            "AND approved_urgency IS NULL)",
            name="ck_reviews_rejected_has_no_routing",
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name="fk_reviews_complaint_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            ["predictions.id"],
            name="fk_reviews_prediction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name="fk_reviews_reviewer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_category_id"],
            ["complaint_categories.id"],
            name="fk_reviews_approved_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_department_id"],
            ["departments.id"],
            name="fk_reviews_approved_department_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_reviews_prediction_id", "reviews", ["prediction_id"], unique=True
    )
    op.create_index(
        "ix_reviews_complaint_id", "reviews", ["complaint_id"], unique=False
    )
    op.create_index(
        "ix_reviews_reviewer_id", "reviews", ["reviewer_id"], unique=False
    )
    op.create_index(
        "ix_reviews_approved_category_id",
        "reviews",
        ["approved_category_id"],
        unique=False,
    )
    op.create_index(
        "ix_reviews_approved_department_id",
        "reviews",
        ["approved_department_id"],
        unique=False,
    )
    op.create_index(
        "ix_reviews_outcome_created_at",
        "reviews",
        ["outcome", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reviews_reviewer_created_at",
        "reviews",
        ["reviewer_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop review indexes, table, and review-outcome enum."""
    op.drop_index("ix_reviews_reviewer_created_at", table_name="reviews")
    op.drop_index("ix_reviews_outcome_created_at", table_name="reviews")
    op.drop_index("ix_reviews_approved_department_id", table_name="reviews")
    op.drop_index("ix_reviews_approved_category_id", table_name="reviews")
    op.drop_index("ix_reviews_reviewer_id", table_name="reviews")
    op.drop_index("ix_reviews_complaint_id", table_name="reviews")
    op.drop_index("uq_reviews_prediction_id", table_name="reviews")
    op.drop_table("reviews")
    _review_outcome.drop(op.get_bind(), checkfirst=False)
