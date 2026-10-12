from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

app_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    pool_recycle=1800,
)

ddl_engine: AsyncEngine = create_async_engine(
    settings.ddl_database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    pool_recycle=1800,
)

app_session_factory = async_sessionmaker(
    app_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_app_db() -> AsyncIterator[AsyncSession]:
    async with app_session_factory() as session:
        yield session


def get_ddl_engine() -> AsyncEngine:
    return ddl_engine


async def dispose_engines() -> None:
    await app_engine.dispose()
    await ddl_engine.dispose()
