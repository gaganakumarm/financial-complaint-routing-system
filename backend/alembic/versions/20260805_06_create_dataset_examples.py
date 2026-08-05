"""Create dataset examples.

Revision ID: 20260805_06
Revises: 20260804_05
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_06"
down_revision: str | None = "20260804_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_urgency = postgresql.ENUM("low", "medium", "high", "critical", name="complaint_urgency", create_type=False)

def upgrade() -> None:
    op.create_table("dataset_examples",
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False), sa.Column("example_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected_category_id", sa.Uuid(), nullable=False), sa.Column("expected_department_id", sa.Uuid(), nullable=False),
        sa.Column("expected_urgency", _urgency, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(example_id) <> ''", name="ck_dataset_examples_example_id_not_blank"), sa.CheckConstraint("btrim(title) <> ''", name="ck_dataset_examples_title_not_blank"), sa.CheckConstraint("btrim(description) <> ''", name="ck_dataset_examples_description_not_blank"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], name="fk_dataset_examples_dataset_version_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expected_category_id"], ["complaint_categories.id"], name="fk_dataset_examples_expected_category_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expected_department_id"], ["departments.id"], name="fk_dataset_examples_expected_department_id", ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"))
    op.create_index("uq_dataset_examples_dataset_example_id", "dataset_examples", ["dataset_version_id", "example_id"], unique=True)
    op.create_index("ix_dataset_examples_dataset_version_id", "dataset_examples", ["dataset_version_id"])
    op.create_index("ix_dataset_examples_expected_category_id", "dataset_examples", ["expected_category_id"])
    op.create_index("ix_dataset_examples_expected_department_id", "dataset_examples", ["expected_department_id"])

def downgrade() -> None:
    op.drop_index("ix_dataset_examples_expected_department_id", table_name="dataset_examples")
    op.drop_index("ix_dataset_examples_expected_category_id", table_name="dataset_examples")
    op.drop_index("ix_dataset_examples_dataset_version_id", table_name="dataset_examples")
    op.drop_index("uq_dataset_examples_dataset_example_id", table_name="dataset_examples")
    op.drop_table("dataset_examples")
