from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Предоставляет асинхронную сессию для обработки HTTP-запроса.

    После завершения работы endpoint сессия автоматически закрывается.
    """
    async with session_factory() as session:
        yield session


# Тип для удобного внедрения AsyncSession в endpoints.
DBSession = Annotated[AsyncSession, Depends(get_db)]
