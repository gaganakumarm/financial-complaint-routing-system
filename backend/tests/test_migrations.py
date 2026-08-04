"""Tests for the Alembic migration infrastructure."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import alembic
import asyncpg
import pytest
import sqlalchemy.ext.asyncio
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy.engine import make_url

import app.models
from app.core.config import Settings
from app.db.base import Base


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SCRIPT_DIRECTORY = BACKEND_ROOT / "alembic"


def make_alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def test_alembic_dependency_and_file_structure() -> None:
    assert alembic.__version__
    assert ALEMBIC_INI.is_file()
    assert SCRIPT_DIRECTORY.is_dir()
    assert (SCRIPT_DIRECTORY / "env.py").is_file()
    assert (SCRIPT_DIRECTORY / "script.py.mako").is_file()
    assert (SCRIPT_DIRECTORY / "versions").is_dir()


def test_alembic_config_and_linear_revision_chain() -> None:
    config = make_alembic_config()
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())

    assert config.get_main_option("script_location") == "alembic"
    assert len(revisions) == 4
    assert [(item.revision, item.down_revision) for item in revisions] == [
        ("20260804_04", "20260804_03"),
        ("20260804_03", "20260804_02"),
        ("20260804_02", "20260803_01"),
        ("20260803_01", None),
    ]
    assert script.get_heads() == ["20260804_04"]
    assert script.get_bases() == ["20260803_01"]


def test_migration_metadata_contains_approved_tables() -> None:
    assert Base.metadata is not None
    assert set(Base.metadata.tables) == {
        "roles",
        "users",
        "complaint_categories",
        "departments",
        "complaints",
        "complaint_status_history",
        "model_versions",
        "predictions",
        "reviews",
    }


def test_committed_config_contains_no_database_credentials() -> None:
    contents = ALEMBIC_INI.read_text(encoding="utf-8")
    configured_url = make_alembic_config().get_main_option("sqlalchemy.url")

    assert configured_url == ""
    assert "postgresql" not in contents
    assert "user:pass" not in contents


def test_settings_database_url_can_be_injected_into_alembic_config() -> None:
    settings = Settings(_env_file=None)
    config = make_alembic_config()
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

    assert make_url(config.get_main_option("sqlalchemy.url")).drivername == (
        "postgresql+asyncpg"
    )


def test_invalid_database_url_remains_rejected() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(database_url="postgresql://localhost/database", _env_file=None)


def test_config_and_script_inspection_do_not_create_an_engine() -> None:
    with patch.object(sqlalchemy.ext.asyncio, "async_engine_from_config") as create:
        config = make_alembic_config()
        ScriptDirectory.from_config(config)

    create.assert_not_called()


def test_offline_migrations_do_not_create_engine_or_connect() -> None:
    config = make_alembic_config()

    with (
        patch.object(sqlalchemy.ext.asyncio, "async_engine_from_config") as create,
        patch.object(asyncpg, "connect", new_callable=AsyncMock) as connect,
    ):
        command.upgrade(config, "head", sql=True)

    create.assert_not_called()
    connect.assert_not_called()


def test_migration_template_has_required_typed_api() -> None:
    template = (SCRIPT_DIRECTORY / "script.py.mako").read_text(encoding="utf-8")

    assert "from alembic import op" in template
    assert "import sqlalchemy as sa" in template
    assert "revision: str" in template
    assert "down_revision:" in template
    assert "branch_labels:" in template
    assert "depends_on:" in template
    assert "def upgrade() -> None:" in template
    assert "def downgrade() -> None:" in template
