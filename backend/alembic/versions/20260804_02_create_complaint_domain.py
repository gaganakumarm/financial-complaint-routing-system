"""Create complaint domain.

Revision ID: 20260804_02
Revises: 20260803_01
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_02"
down_revision: str | None = "20260803_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_complaint_status = postgresql.ENUM(
    "submitted",
    "prediction_pending",
    "prediction_completed",
    "awaiting_review",
    "under_review",
    "routed",
    "closed",
    "prediction_failed",
    name="complaint_status",
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
_complaint_change_source = postgresql.ENUM(
    "customer",
    "reviewer",
    "administrator",
    "system",
    "model_pipeline",
    name="complaint_change_source",
    create_type=False,
)


def upgrade() -> None:
    """Create complaint lifecycle enums, tables, constraints, and indexes."""
    bind = op.get_bind()
    _complaint_status.create(bind, checkfirst=False)
    _complaint_urgency.create(bind, checkfirst=False)
    _complaint_change_source.create(bind, checkfirst=False)

    op.create_table(
        "complaint_categories",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_high_risk",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "btrim(code) <> ''",
            name="ck_complaint_categories_code_not_blank",
        ),
        sa.CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_complaint_categories_display_name_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "departments",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(code) <> ''", name="ck_departments_code_not_blank"),
        sa.CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_departments_display_name_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "complaints",
        sa.Column("reference_number", sa.String(length=50), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "current_status",
            _complaint_status,
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("final_category_id", sa.Uuid(), nullable=True),
        sa.Column("final_department_id", sa.Uuid(), nullable=True),
        sa.Column("final_urgency", _complaint_urgency, nullable=True),
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "btrim(reference_number) <> ''",
            name="ck_complaints_reference_number_not_blank",
        ),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_complaints_title_not_blank"),
        sa.CheckConstraint(
            "btrim(description) <> ''",
            name="ck_complaints_description_not_blank",
        ),
        sa.CheckConstraint(
            "review_completed_at IS NULL OR review_started_at IS NULL "
            "OR review_completed_at >= review_started_at",
            name="ck_complaints_review_timestamps_order",
        ),
        sa.CheckConstraint(
            "current_status <> 'routed' OR "
            "(final_category_id IS NOT NULL AND final_department_id IS NOT NULL "
            "AND final_urgency IS NOT NULL)",
            name="ck_complaints_routed_requires_final_routing",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_complaints_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["final_category_id"],
            ["complaint_categories.id"],
            name="fk_complaints_final_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["final_department_id"],
            ["departments.id"],
            name="fk_complaints_final_department_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "complaint_status_history",
        sa.Column("complaint_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", _complaint_status, nullable=True),
        sa.Column("new_status", _complaint_status, nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("change_source", _complaint_change_source, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["complaint_id"],
            ["complaints.id"],
            name="fk_complaint_status_history_complaint_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_complaint_status_history_changed_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "uq_complaint_categories_code",
        "complaint_categories",
        ["code"],
        unique=True,
    )
    op.create_index("uq_departments_code", "departments", ["code"], unique=True)
    op.create_index(
        "uq_complaints_reference_number",
        "complaints",
        ["reference_number"],
        unique=True,
    )
    op.create_index(
        "ix_complaints_customer_id", "complaints", ["customer_id"], unique=False
    )
    op.create_index(
        "ix_complaints_customer_created_at",
        "complaints",
        ["customer_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_complaints_review_queue",
        "complaints",
        ["current_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_complaints_final_category_id",
        "complaints",
        ["final_category_id"],
        unique=False,
    )
    op.create_index(
        "ix_complaints_final_department_id",
        "complaints",
        ["final_department_id"],
        unique=False,
    )
    op.create_index(
        "ix_complaint_status_history_complaint_created_at",
        "complaint_status_history",
        ["complaint_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_complaint_status_history_changed_by_user_id",
        "complaint_status_history",
        ["changed_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop complaint lifecycle indexes, tables, and enums safely."""
    op.drop_index(
        "ix_complaint_status_history_changed_by_user_id",
        table_name="complaint_status_history",
    )
    op.drop_index(
        "ix_complaint_status_history_complaint_created_at",
        table_name="complaint_status_history",
    )
    op.drop_table("complaint_status_history")

    op.drop_index("ix_complaints_final_department_id", table_name="complaints")
    op.drop_index("ix_complaints_final_category_id", table_name="complaints")
    op.drop_index("ix_complaints_review_queue", table_name="complaints")
    op.drop_index("ix_complaints_customer_created_at", table_name="complaints")
    op.drop_index("ix_complaints_customer_id", table_name="complaints")
    op.drop_index("uq_complaints_reference_number", table_name="complaints")
    op.drop_table("complaints")

    op.drop_index("uq_departments_code", table_name="departments")
    op.drop_table("departments")
    op.drop_index(
        "uq_complaint_categories_code",
        table_name="complaint_categories",
    )
    op.drop_table("complaint_categories")

    bind = op.get_bind()
    _complaint_change_source.drop(bind, checkfirst=False)
    _complaint_urgency.drop(bind, checkfirst=False)
    _complaint_status.drop(bind, checkfirst=False)
