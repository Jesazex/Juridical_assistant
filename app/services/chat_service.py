"""Owner-scoped asynchronous chat operations. The caller owns the transaction."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.core.datetime import utc_now


class ChatNotFound(Exception):
    pass


async def get_chat(session: AsyncSession, owner_id: str, chat_id: int) -> Chat:
    chat = await session.scalar(select(Chat).where(Chat.id == chat_id, Chat.owner_id == owner_id))
    if chat is None:
        raise ChatNotFound
    return chat


async def create_chat(session: AsyncSession, owner_id: str, title: str | None) -> Chat:
    chat = Chat(owner_id=owner_id, title=title if title is not None else "Новый чат")
    session.add(chat)
    chat.title_is_manual = title is not None
    await session.flush()
    return chat


async def list_chats(session: AsyncSession, owner_id: str, limit: int, offset: int):
    total = await session.scalar(select(func.count()).select_from(Chat).where(Chat.owner_id == owner_id))
    items = await session.scalars(
        select(Chat).where(Chat.owner_id == owner_id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc()).limit(limit).offset(offset)
    )
    return {"items": list(items), "total": total, "limit": limit, "offset": offset}


async def rename_chat(session: AsyncSession, owner_id: str, chat_id: int, title: str) -> Chat:
    chat = await get_chat(session, owner_id, chat_id)
    chat.title = title
    chat.title_is_manual = True
    chat.updated_at = utc_now()
    await session.flush()
    return chat


async def delete_chat(session: AsyncSession, owner_id: str, chat_id: int) -> None:
    chat = await get_chat(session, owner_id, chat_id)
    await session.delete(chat)
    await session.flush()
