"""
Database configuration and connection management
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# SQLAlchemy engine and session factory
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    future=True,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_session():
    """
    Async session dependency for FastAPI.
    
    Yields:
        AsyncSession: Database session
    """
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
