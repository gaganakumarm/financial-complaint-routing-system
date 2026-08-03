"""Lazy asynchronous database session providers."""

from collections.abc import AsyncGenerator
from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine


@cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and cache the asynchronous session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and always close it after use."""
    async with get_session_factory()() as session:
        yield session
