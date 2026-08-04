"""Tests for the Role and User identity schema."""

from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.models import Role, User


ROLE_COLUMNS = {
    "id",
    "name",
    "display_name",
    "description",
    "is_active",
    "created_at",
    "updated_at",
}
USER_COLUMNS = {
    "id",
    "role_id",
    "email",
    "password_hash",
    "full_name",
    "is_active",
    "email_verified",
    "last_login_at",
    "created_at",
    "updated_at",
}


def test_identity_models_register_their_expected_tables() -> None:
    assert {Role.__table__.name, User.__table__.name} == {"roles", "users"}
    assert Role.__table__ is Base.metadata.tables["roles"]
    assert User.__table__ is Base.metadata.tables["users"]


def test_role_schema() -> None:
    table = Role.__table__

    assert table.name == "roles"
    assert set(table.c.keys()) == ROLE_COLUMNS
    assert table.c.id.primary_key is True
    assert table.c.id.type.python_type is UUID
    assert isinstance(table.c.name.type, String)
    assert table.c.name.type.length == 50
    assert table.c.name.nullable is False
    assert table.c.display_name.type.length == 100
    assert table.c.display_name.nullable is False
    assert isinstance(table.c.description.type, Text)
    assert table.c.description.nullable is True
    assert isinstance(table.c.is_active.type, Boolean)
    assert table.c.is_active.nullable is False
    assert table.c.is_active.default.arg is True
    assert str(table.c.is_active.server_default.arg).lower() == "true"

    for name in ("created_at", "updated_at"):
        assert isinstance(table.c[name].type, DateTime)
        assert table.c[name].type.timezone is True
        assert table.c[name].nullable is False

    indexes = {index.name: index for index in table.indexes}
    assert indexes["uq_roles_name"].unique is True
    assert [column.name for column in indexes["uq_roles_name"].columns] == ["name"]
    assert _check_constraint_names(table) == {
        "ck_roles_name_not_blank",
        "ck_roles_display_name_not_blank",
    }


def test_user_schema() -> None:
    table = User.__table__

    assert table.name == "users"
    assert set(table.c.keys()) == USER_COLUMNS
    assert table.c.id.primary_key is True
    assert table.c.id.type.python_type is UUID
    assert table.c.role_id.nullable is False

    foreign_key = next(iter(table.c.role_id.foreign_keys))
    assert foreign_key.target_fullname == "roles.id"
    assert foreign_key.ondelete == "RESTRICT"
    assert foreign_key.constraint.name == "fk_users_role_id_roles"

    assert table.c.email.type.length == 320
    assert table.c.email.nullable is False
    assert table.c.password_hash.type.length == 255
    assert table.c.password_hash.nullable is False
    assert table.c.full_name.type.length == 200
    assert table.c.full_name.nullable is False
    assert isinstance(table.c.last_login_at.type, DateTime)
    assert table.c.last_login_at.type.timezone is True
    assert table.c.last_login_at.nullable is True

    assert table.c.is_active.default.arg is True
    assert str(table.c.is_active.server_default.arg).lower() == "true"
    assert table.c.email_verified.default.arg is False
    assert str(table.c.email_verified.server_default.arg).lower() == "false"

    indexes = {index.name: index for index in table.indexes}
    assert indexes["ix_users_role_id"].unique is False
    assert [column.name for column in indexes["ix_users_role_id"].columns] == [
        "role_id"
    ]
    email_index = indexes["uq_users_email_lower"]
    assert email_index.unique is True
    expression = str(email_index.expressions[0].compile(dialect=postgresql.dialect()))
    assert expression == "lower(users.email)"
    assert _check_constraint_names(table) == {
        "ck_users_email_not_blank",
        "ck_users_password_hash_not_blank",
        "ck_users_full_name_not_blank",
    }
    assert "password" not in table.c
    assert not hasattr(User, "password")


def test_role_user_relationship_is_bidirectional_without_delete_cascade() -> None:
    role = Role(name="reviewer", display_name="Reviewer")
    user = User(
        role=role,
        email="reviewer@example.com",
        password_hash="hashed-value",
        full_name="Example Reviewer",
    )

    assert user.role is role
    assert user in role.users
    assert User.role.property.back_populates == "users"
    assert Role.users.property.back_populates == "role"
    assert "delete" not in Role.users.property.cascade
    assert "delete-orphan" not in Role.users.property.cascade


def test_identity_migration_operations(monkeypatch) -> None:
    config = Config("alembic.ini")
    revision = ScriptDirectory.from_config(config).get_revision("20260803_01")
    assert revision is not None
    module = revision.module
    operations: list[tuple[str, str]] = []

    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda name, *args, **kwargs: operations.append(("create_table", name)),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, *args, **kwargs: operations.append(("create_index", name)),
    )
    monkeypatch.setattr(
        module.op,
        "drop_index",
        lambda name, *args, **kwargs: operations.append(("drop_index", name)),
    )
    monkeypatch.setattr(
        module.op,
        "drop_table",
        lambda name, *args, **kwargs: operations.append(("drop_table", name)),
    )

    module.upgrade()
    assert [value for operation, value in operations if operation == "create_table"] == [
        "roles",
        "users",
    ]
    assert [value for operation, value in operations if operation == "create_index"] == [
        "uq_roles_name",
        "ix_users_role_id",
        "uq_users_email_lower",
    ]

    operations.clear()
    module.downgrade()
    assert operations == [
        ("drop_index", "uq_users_email_lower"),
        ("drop_index", "ix_users_role_id"),
        ("drop_table", "users"),
        ("drop_index", "uq_roles_name"),
        ("drop_table", "roles"),
    ]


def _check_constraint_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
