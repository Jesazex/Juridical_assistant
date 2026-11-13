
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.config import get_settings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlite3 import Connection as SQLiteConnection
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, connection_record):
    if isinstance(connection, (SQLiteConnection, AsyncAdapt_aiosqlite_connection)):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


settings = get_settings()


# Асинхронный движок для взаимодействия с базой данных.
# SQL-вывод не зависит от debug приложения: параметры могут содержать
# юридическую переписку. Скрываем их также в сообщениях об ошибках SQLAlchemy.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    hide_parameters=True,
)


# Фабрика для создания новых асинхронных сессий.
session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def close_db() -> None:
    """Закрывает пул соединений при завершении приложения."""
    await engine.dispose()
