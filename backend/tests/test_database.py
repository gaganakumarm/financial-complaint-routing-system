"""Tests for reusable asynchronous database infrastructure."""

import asyncio
import importlib
from datetime import timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

import asyncpg
import pytest
import sqlalchemy.ext.asyncio
from pydantic import ValidationError
from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import app.models
from app.core.config import Settings
from app.db.base import Base
from app.db import engine as engine_module
from app.db import session as session_module
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/financial_complaints"
)


@pytest.fixture(autouse=True)
def clear_database_caches() -> None:
    session_module.get_session_factory.cache_clear()
    engine_module.get_engine.cache_clear()
    yield
    session_module.get_session_factory.cache_clear()
    if engine_module.get_engine.cache_info().currsize:
        asyncio.run(engine_module.get_engine().dispose())
    engine_module.get_engine.cache_clear()


def test_default_database_url() -> None:
    assert Settings(_env_file=None).database_url == DEFAULT_DATABASE_URL


def test_database_url_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+asyncpg://user:password@db:5432/app"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert Settings(_env_file=None).database_url == database_url


def test_database_url_whitespace_is_trimmed() -> None:
    settings = Settings(database_url=f"  {DEFAULT_DATABASE_URL}  ", _env_file=None)

    assert settings.database_url == DEFAULT_DATABASE_URL


@pytest.mark.parametrize("database_url", ["", "   "])
def test_empty_database_url_is_rejected(database_url: str) -> None:
    with pytest.raises(ValidationError, match="database URL cannot be empty"):
        Settings(database_url=database_url, _env_file=None)


def test_database_url_requires_asyncpg_driver() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(
            database_url="postgresql://postgres:postgres@localhost/database",
            _env_file=None,
        )


def test_settings_construction_does_not_connect() -> None:
    with patch.object(asyncpg, "connect", new_callable=AsyncMock) as connect:
        Settings(_env_file=None)

    connect.assert_not_called()


def test_importing_engine_module_does_not_create_engine() -> None:
    with patch.object(sqlalchemy.ext.asyncio, "create_async_engine") as create_engine:
        importlib.reload(engine_module)

    create_engine.assert_not_called()
    importlib.reload(engine_module)


def test_engine_is_async_lazy_and_cached() -> None:
    with patch.object(asyncpg, "connect", new_callable=AsyncMock) as connect:
        engine = engine_module.get_engine()

    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.dialect.is_async is True
    assert engine_module.get_engine() is engine
    connect.assert_not_called()


def test_engine_echo_follows_debug_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(debug=True, _env_file=None)
    monkeypatch.setattr(engine_module, "get_settings", lambda: settings)

    assert engine_module.get_engine().echo is True


def test_session_factory_configuration() -> None:
    factory = session_module.get_session_factory()

    assert isinstance(factory, async_sessionmaker)
    assert session_module.get_session_factory() is factory
    assert factory.kw["autoflush"] is False
    assert factory.kw["expire_on_commit"] is False

    session = factory()
    assert isinstance(session, AsyncSession)
    asyncio.run(session.close())


@pytest.mark.anyio
async def test_session_dependency_yields_and_closes_without_connecting() -> None:
    with patch.object(asyncpg, "connect", new_callable=AsyncMock) as connect:
        dependency = session_module.get_db_session()
        session = await anext(dependency)
        close = AsyncMock(wraps=session.close)
        session.close = close
        await dependency.aclose()

    assert isinstance(session, AsyncSession)
    close.assert_awaited_once()
    connect.assert_not_called()


def test_declarative_base_has_metadata() -> None:
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
            "dataset_versions",
            "dataset_examples",
        "benchmark_experiments",
        "benchmark_results",
        "benchmark_comparisons",
        "benchmark_comparison_members",
        "benchmark_example_results",
        "model_promotion_decisions",
    }


def test_uuid_and_timestamp_mixins() -> None:
    class TestBase(DeclarativeBase):
        pass

    class Example(UUIDPrimaryKeyMixin, TimestampMixin, TestBase):
        __tablename__ = "example"

    id_column = Example.__table__.c.id
    created_at = Example.__table__.c.created_at
    updated_at = Example.__table__.c.updated_at

    generated_id = id_column.default.arg(None)
    assert id_column.primary_key is True
    assert id_column.type.python_type is UUID
    assert isinstance(generated_id, UUID)
    assert generated_id.version == 4

    for column in (created_at, updated_at):
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True
        assert column.nullable is False
    assert updated_at.onupdate is not None


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    value = utc_now()

    assert value.tzinfo is timezone.utc
    assert value.utcoffset() is not None
