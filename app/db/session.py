import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _parse_database_url(value: str | URL) -> URL:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("PSB_DATABASE_URL is invalid") from None
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("PSB_DATABASE_URL must use postgresql+asyncpg")
    return url


def get_database_url() -> URL:
    value = os.environ.get("PSB_DATABASE_URL")
    if value is None:
        env_file = Path(__file__).resolve().parents[2] / ".env"
        value = dotenv_values(env_file, interpolate=False).get("PSB_DATABASE_URL")
    if not value:
        raise RuntimeError("Set PSB_DATABASE_URL in the environment or the project's .env")
    return _parse_database_url(value)


def create_database_engine(database_url: str | URL | None = None) -> AsyncEngine:
    url = get_database_url() if database_url is None else _parse_database_url(database_url)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"server_settings": {"search_path": "pg_catalog,public", "timezone": "UTC"}},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
