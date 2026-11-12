from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
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


async def get_anon_id(anon_id: Annotated[str | None, Cookie()] = None) -> str:
    if anon_id is None or not anon_id.strip():
        raise HTTPException(status_code=401, detail="anon_id cookie is required")
    return anon_id


AnonId = Annotated[str, Depends(get_anon_id)]
