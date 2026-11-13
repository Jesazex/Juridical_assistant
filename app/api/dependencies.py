from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    ANONYMOUS_COOKIE,
    ANONYMOUS_COOKIE_MAX_AGE,
    anonymous_token,
    token_hash,
)
from app.db.repositories.chat_repository import upsert_anonymous_user
from app.services.chat_service import ChatNotFound


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_owner_id(request: Request, response: Response, db: DBSession) -> UUID:
    token, needs_cookie = anonymous_token(request.cookies.get(ANONYMOUS_COOKIE))
    async with db.begin():
        owner = await upsert_anonymous_user(db, token_hash(token))
        owner_id = owner.id
    if needs_cookie:
        response.set_cookie(
            ANONYMOUS_COOKIE,
            token,
            max_age=ANONYMOUS_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
            secure=request.app.state.cookie_secure or request.url.scheme == "https",
        )
    return owner_id


OwnerId = Annotated[UUID, Depends(get_owner_id)]


def chat_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Chat not found")


@asynccontextmanager
async def chat_transaction(db: AsyncSession) -> AsyncIterator[None]:
    """Commit successful chat operations and roll back before translating errors."""
    try:
        async with db.begin():
            yield
    except ChatNotFound as exc:
        raise chat_not_found() from exc
