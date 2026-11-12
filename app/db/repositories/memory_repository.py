from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, ChatMemory, Message
from app.rag.common.embeddings import validate_embedding


async def save_chat_memory(
    session: AsyncSession,
    owner_id: UUID,
    chat_id: UUID,
    content: str,
    *,
    memory_type: str = "context",
    source_message_id: UUID | None = None,
    embedding: Sequence[float] | None = None,
) -> ChatMemory | None:
    """Store context extracted from user messages. The caller owns the transaction."""
    if memory_type not in {"context", "summary"} or not content.strip():
        raise ValueError("Provide nonblank context or summary text")
    chat = await session.scalar(
        select(Chat.id).where(Chat.id == chat_id, Chat.owner_id == owner_id).with_for_update()
    )
    if chat is None:
        return None
    if source_message_id is not None:
        source = await session.scalar(
            select(Message.id)
            .where(Message.id == source_message_id, Message.chat_id == chat_id, Message.role == "user")
            .with_for_update(read=True, key_share=True)
        )
        if source is None:
            raise ValueError("Memory source must be a user message in the same chat")

    item = ChatMemory(
        chat_id=chat_id,
        source_message_id=source_message_id,
        memory_type=memory_type,
        content=content.strip(),
        embedding=validate_embedding(embedding) if embedding is not None else None,
    )
    session.add(item)
    await session.flush()
    return item
