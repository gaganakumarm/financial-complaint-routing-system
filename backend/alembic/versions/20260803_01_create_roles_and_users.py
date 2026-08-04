"""Create roles and users.

Revision ID: 20260803_01
Revises:
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the roles and users identity tables."""
    op.create_table(
        "roles",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_roles_name_not_blank"),
        sa.CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_roles_display_name_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(email) <> ''", name="ck_users_email_not_blank"),
        sa.CheckConstraint(
            "btrim(password_hash) <> ''",
            name="ck_users_password_hash_not_blank",
        ),
        sa.CheckConstraint(
            "btrim(full_name) <> ''",
            name="ck_users_full_name_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_users_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    """Drop the users and roles identity tables."""
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_table("users")
    op.drop_index("uq_roles_name", table_name="roles")
    op.drop_table("roles")
