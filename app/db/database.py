"""
Database configuration and connection management
"""

from __future__ import annotations

import logging
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.db.database_url import database_requires_ssl, normalize_database_url

logger = logging.getLogger(__name__)

_ASYNC_URL = normalize_database_url(settings.DATABASE_URL)


def _connect_args() -> dict:
    if database_requires_ssl(_ASYNC_URL):
        ctx = ssl.create_default_context()
        # Railway / managed PG often use certs that need default context
        return {"ssl": ctx}
    return {}


# SQLAlchemy engine and session factory
engine = create_async_engine(
    _ASYNC_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args=_connect_args(),
    future=True,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

logger.info(
    "Database engine configured (ssl=%s)",
    bool(_connect_args()),
)


async def get_session():
    """
    Async session dependency for FastAPI.
    Yields None when database is unavailable (mock fallback mode).
    """
    from app.db.init_db import is_db_ready

    if not is_db_ready():
        yield None
        return
    async with async_session_maker() as session:
        yield session


async def create_db_tables():
    """
    Create database tables.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db_tables():
    """
    Drop database tables (for testing).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
