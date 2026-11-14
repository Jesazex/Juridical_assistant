"""Owner-scoped message operations; the caller owns the transaction."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.message import Message
from app.db.repositories import message_repository
from app.db.repositories.message_repository import PendingAnswer
from app.schemas.message import MessageResponse
from app.services.chat_service import ChatNotFound


class MessageNotFound(Exception):
    """The message is missing or inaccessible to the owner."""


class MessageNotRetryable(Exception):
    """Only a failed assistant answer can be retried."""


async def _history(session: AsyncSession, owner_id: UUID, chat_id: UUID) -> list[Message]:
    messages = await message_repository.list_owned_messages(session, chat_id, owner_id)
    if messages is None:
        raise ChatNotFound
    return messages


async def list_messages(
    session: AsyncSession, owner_id: UUID, chat_id: UUID, limit: int = 50, offset: int = 0,
) -> tuple[list[MessageResponse], int]:
    messages = await _history(session, owner_id, chat_id)
    # TODO: Move pagination and total counting into the repository.
    items = []
    for message in messages[offset:offset + limit]:
        citations = []
        if message.role == "assistant" and message.status == "completed":
            # TODO: Batch-load citations in the repository to avoid N+1 queries.
            citations = await message_repository.list_answer_citations(
                session, chat_id, owner_id, message.id,
            )
        items.append(MessageResponse.from_message(message, citations))
    return items, len(messages)


async def _start_answer(
    session: AsyncSession, owner_id: UUID, chat_id: UUID, question_id: UUID,
) -> PendingAnswer:
    pending = await message_repository.create_pending_answer(
        session, chat_id, owner_id, question_id,
    )
    if pending is None:
        raise MessageNotFound
    if pending.started_at is None:
        # Another request already started or completed this answer under the chat lock.
        raise MessageNotRetryable
    return pending


async def send_message(
    session: AsyncSession, owner_id: UUID, chat_id: UUID, content: str,
) -> tuple[Message, PendingAnswer]:
    question = await message_repository.save_user_message(session, chat_id, owner_id, content)
    if question is None:
        raise ChatNotFound
    answer = await _start_answer(session, owner_id, chat_id, question.id)
    return question, answer


async def retry_message(
    session: AsyncSession, owner_id: UUID, chat_id: UUID, message_id: UUID,
) -> PendingAnswer:
    # TODO: Replace history scanning with an owner-scoped repository message lookup.
    messages = await _history(session, owner_id, chat_id)
    answer = next((message for message in messages if message.id == message_id), None)
    if answer is None:
        raise MessageNotFound
    if answer.role != "assistant" or answer.status != "failed" or answer.reply_to_message_id is None:
        raise MessageNotRetryable
    return await _start_answer(session, owner_id, chat_id, answer.reply_to_message_id)


async def process_pending_answer(
    session_factory: async_sessionmaker[AsyncSession],
    owner_id: UUID,
    chat_id: UUID,
    message_id: UUID,
    attempt_started_at: datetime,
) -> None:
    """Process an already committed attempt using a session independent of HTTP."""
    # TODO: Connect Answer Service here, outside a DB transaction. Persist its result
    # with complete_answer(..., attempt_started_at=...) or fail_answer on failure.
    async with session_factory() as session:
        async with session.begin():
            await message_repository.fail_answer(
                session, chat_id, owner_id, message_id, "generation_unavailable",
                attempt_started_at=attempt_started_at,
            )
