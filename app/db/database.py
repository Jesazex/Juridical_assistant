
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.config import get_settings
from sqlalchemy.orm import DeclarativeBase


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
