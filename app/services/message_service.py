"""Commit input and pending reply before generation; persist its outcome separately."""
from uuid import UUID
import logging

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utc_now
from app.db.models.message import Message
from app.schemas.message import MessageExchangeResponse, MessageResponse, MessageSource
from app.services import ai_service, chat_service

logger = logging.getLogger(__name__)


async def list_messages(db: AsyncSession, owner_id: str, chat_id: UUID,
                        limit: int = 50, offset: int = 0):
    await chat_service.get_chat(db, owner_id, chat_id)
    total = await db.scalar(select(func.count()).select_from(Message).where(Message.chat_id == chat_id))
    items = await db.scalars(select(Message).where(Message.chat_id == chat_id)
                            .order_by(Message.created_at, Message.id).limit(limit).offset(offset))
    return {"items": list(items), "total": total, "limit": limit, "offset": offset}


async def create_message(db: AsyncSession, owner_id: str, chat_id: UUID, content: str,
                         history: list[dict] | None = None) -> MessageExchangeResponse:
    async with db.begin():
        chat = await chat_service.get_chat(db, owner_id, chat_id)
        first = await db.scalar(select(Message.id).where(
            Message.chat_id == chat_id, Message.role == "user").limit(1)) is None
        if first and not chat.title_is_manual:
            chat.title = " ".join(content.split())[:100]
        chat.updated_at = utc_now()
        user = Message(chat_id=chat_id, role="user", content=content, status="completed")
        assistant = Message(chat_id=chat_id, role="assistant", content="", status="pending")
        db.add_all([user, assistant])
        await db.flush()
        user_result = MessageResponse.model_validate(user)
        assistant_id = assistant.id

    payload = {"chat_id": str(chat_id), "message": {"id": str(user_result.id), "content": content}}
    if history is not None:
        payload["history"] = history
    try:
        result = await ai_service.generate_reply(payload)
        if not isinstance(result["content"], str) or not result["content"].strip():
            raise ValueError("AI returned empty content")
        sources = TypeAdapter(list[MessageSource]).validate_python(result.get("sources", []))
        reply_content = result["content"]
        reply_sources = [source.model_dump(exclude_none=True) for source in sources]
        status = "completed"
    except Exception:
        # Do not log exception text: provider errors may contain private message content.
        logger.warning("AI generation failed for chat %s", chat_id)
        reply_content, reply_sources, status = "", [], "failed"

    async with db.begin():
        # Recheck after generation: deletion of the chat must not resurrect its messages.
        chat = await chat_service.get_chat(db, owner_id, chat_id)
        assistant = await db.scalar(select(Message).where(Message.id == assistant_id)
                                    .execution_options(populate_existing=True))
        assistant.content, assistant.sources, assistant.status = reply_content, reply_sources, status
        assistant.updated_at = utc_now()
        chat.updated_at = utc_now()
        await db.flush()
        assistant_result = MessageResponse.model_validate(assistant)
    return MessageExchangeResponse(user_message=user_result, assistant_message=assistant_result)
