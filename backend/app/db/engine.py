"""Lazy asynchronous SQLAlchemy engine provider."""

from functools import cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings


@cache
def get_engine() -> AsyncEngine:
    """Create and cache the application's asynchronous database engine."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        future=True,
        pool_pre_ping=True,
    )
