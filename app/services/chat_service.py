"""Owner-scoped chat operations; transactions belong to the API layer."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.repositories import chat_repository


class ChatNotFound(Exception):
    """The requested chat does not exist or belongs to another owner."""


async def create_chat(session: AsyncSession, owner_id: UUID, title: str | None = None) -> Chat:
    return await chat_repository.create_chat(session, owner_id, title)


async def list_chats(
    session: AsyncSession, owner_id: UUID, limit: int = 20, offset: int = 0
) -> tuple[list[Chat], int]:
    return await chat_repository.list_owned_chats(session, owner_id, limit, offset)


async def get_chat(session: AsyncSession, owner_id: UUID, chat_id: UUID) -> Chat:
    chat = await chat_repository.get_owned_chat(session, chat_id, owner_id)
    if chat is None:
        raise ChatNotFound
    return chat


async def rename_chat(session: AsyncSession, owner_id: UUID, chat_id: UUID, title: str) -> Chat:
    chat = await chat_repository.rename_owned_chat(session, chat_id, owner_id, title)
    if chat is None:
        raise ChatNotFound
    return chat


async def delete_chat(session: AsyncSession, owner_id: UUID, chat_id: UUID) -> None:
    if not await chat_repository.delete_owned_chat(session, chat_id, owner_id):
        raise ChatNotFound
