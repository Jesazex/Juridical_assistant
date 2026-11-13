from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import session_factory
from app.services.chat_service import ChatNotFound


@asynccontextmanager
async def chat_transaction(db: AsyncSession):
    """Shared API transaction boundary translating unavailable chats to HTTP 404."""
    try:
        async with db.begin():
            yield
    except ChatNotFound:
        raise HTTPException(status_code=404, detail="Chat not found") from None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Предоставляет асинхронную сессию для обработки HTTP-запроса.

    После завершения работы endpoint сессия автоматически закрывается.
    """
    async with session_factory() as session:
        yield session


# Тип для удобного внедрения AsyncSession в endpoints.
DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_anon_id(request: Request) -> str:
    return request.state.anon_id


AnonId = Annotated[str, Depends(get_anon_id)]
