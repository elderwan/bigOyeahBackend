import asyncio
import ssl
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if settings.database_ssl_required:
    if not settings.database_ssl_ca:
        raise RuntimeError(
            "DATABASE_SSL_CA must point to Aiven's official ca.pem file when "
            "DATABASE_SSL_REQUIRED=true"
        )

    ca_path = Path(settings.database_ssl_ca).expanduser()
    if not ca_path.is_file():
        raise RuntimeError(
            f"DATABASE_SSL_CA does not exist: {ca_path}. Download Aiven's official "
            "ca.pem certificate and configure its path in .env"
        )

    ssl_context = ssl.create_default_context(cafile=str(ca_path))
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    connect_args = {"ssl": ssl_context}
else:
    connect_args = {}

app_engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    # aiomysql 0.2.0 exposes ping(reconnect), which is incompatible with
    # SQLAlchemy's async pool pre-ping call. Recycling avoids stale long-lived
    # connections without triggering that broken ping path.
    pool_pre_ping=False,
    pool_recycle=1800,
    connect_args=connect_args,
)

ddl_engine: AsyncEngine = create_async_engine(
    settings.ddl_database_url,
    echo=settings.sql_echo,
    pool_pre_ping=False,
    pool_recycle=1800,
    connect_args=connect_args,
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
