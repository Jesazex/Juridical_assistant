from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer_citation import AnswerCitation
from app.db.models.chat import Chat
from app.db.models.document import Document
from app.db.models.document_chunk import DocumentChunk
from app.db.models.document_version import DocumentVersion
from app.db.models.message import Message
from app.db.repositories.chat_repository import get_owned_chat

AUTO_TITLE_LENGTH = 80
CITATION_PREVIEW_LENGTH = 320


@dataclass(frozen=True)
class PendingAnswer:
    message: Message
    started_at: datetime | None


async def list_owned_messages(
    session: AsyncSession, chat_id: UUID, owner_id: UUID
) -> list[Message] | None:
    result = await session.execute(
        select(Chat.id, Message)
        .outerjoin(Message, Message.chat_id == Chat.id)
        .where(Chat.id == chat_id, Chat.owner_id == owner_id)
        .order_by(Message.created_at, Message.id)
    )
    rows = result.all()
    if not rows:
        return None
    return [message for _, message in rows if message is not None]


async def save_user_message(
    session: AsyncSession, chat_id: UUID, owner_id: UUID, content: str
) -> Message | None:
    if not content.strip():
        raise ValueError("Message content cannot be blank")
    chat = await get_owned_chat(session, chat_id, owner_id, for_update=True)
    if chat is None:
        return None

    if not chat.is_title_custom:
        has_user_message = await session.scalar(
            select(
                select(Message.id)
                .where(Message.chat_id == chat_id, Message.role == "user")
                .exists()
            )
        )
        if not has_user_message:
            chat.title = " ".join(content.split())[:AUTO_TITLE_LENGTH].rstrip()

    now = await session.scalar(select(func.clock_timestamp()))
    message = Message(
        chat_id=chat_id, role="user", content=content, created_at=now, updated_at=now
    )
    chat.updated_at = now
    session.add(message)
    await session.flush()
    return message


async def create_pending_answer(
    session: AsyncSession, chat_id: UUID, owner_id: UUID, reply_to_message_id: UUID
) -> PendingAnswer | None:
    """Start or retry one answer per question. Commit before calling the model."""
    chat = await get_owned_chat(session, chat_id, owner_id, for_update=True)
    if chat is None:
        return None
    question_id = await session.scalar(
        select(Message.id).where(
            Message.id == reply_to_message_id, Message.chat_id == chat_id, Message.role == "user"
        )
    )
    if question_id is None:
        return None

    answer = await session.scalar(
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.reply_to_message_id == question_id,
            Message.role == "assistant",
        )
        .execution_options(populate_existing=True)
    )
    if answer is not None and answer.status != "failed":
        return PendingAnswer(message=answer, started_at=None)

    now = await session.scalar(select(func.clock_timestamp()))
    if answer is None:
        answer = Message(
            chat_id=chat_id,
            reply_to_message_id=question_id,
            role="assistant",
            status="pending",
            content="",
            created_at=now,
            updated_at=now,
        )
        session.add(answer)
        chat.updated_at = now
    else:
        now = max(now, answer.updated_at + timedelta(microseconds=1))
        answer.status = "pending"
        answer.content = ""
        answer.error_code = None
        answer.updated_at = now
    await session.flush()
    return PendingAnswer(message=answer, started_at=now)


async def _pending_attempt(
    session: AsyncSession,
    chat_id: UUID,
    owner_id: UUID,
    message_id: UUID,
    attempt_started_at: datetime,
) -> Message | None:
    # Serialize with retry and chat deletion using the same chat row lock.
    if await get_owned_chat(session, chat_id, owner_id, for_update=True) is None:
        return None
    return await session.scalar(
        select(Message)
        .where(
            Message.id == message_id,
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.status == "pending",
            Message.updated_at == attempt_started_at,
        )
        .execution_options(populate_existing=True)
    )


async def complete_answer(
    session: AsyncSession,
    chat_id: UUID,
    owner_id: UUID,
    message_id: UUID,
    content: str,
    *,
    attempt_started_at: datetime,
    citations: Sequence[UUID] = (),
) -> Message | None:
    """Save the answer and snapshots for the chunk IDs vetted by the caller."""
    if not content.strip():
        raise ValueError("Completed answer content cannot be blank")
    answer = await _pending_attempt(session, chat_id, owner_id, message_id, attempt_started_at)
    if answer is None:
        return None

    citation_ids = tuple(dict.fromkeys(citations))
    sources = {}
    if citation_ids:
        rows = await session.execute(
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.section_path,
                DocumentChunk.page_from,
                DocumentChunk.content,
                Document.id.label("document_id"),
                Document.title,
            )
            .select_from(DocumentChunk)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentChunk.id.in_(citation_ids))
        )
        sources = {source.chunk_id: source for source in rows}
        if len(sources) != len(citation_ids):
            raise ValueError("A citation references an unknown document chunk")

    now = await session.scalar(select(func.clock_timestamp()))
    answer.content = content
    answer.status = "completed"
    answer.updated_at = now

    for position, chunk_id in enumerate(citation_ids):
        source = sources[chunk_id]
        session.add(
            AnswerCitation(
                message_id=message_id,
                chunk_id=chunk_id,
                position=position,
                document_id_snapshot=str(source.document_id),
                document_title_snapshot=source.title,
                section_snapshot=source.section_path,
                page_snapshot=source.page_from,
                excerpt_snapshot=source.content.strip()[:CITATION_PREVIEW_LENGTH].rstrip(),
            )
        )
    await session.flush()
    return answer


async def fail_answer(
    session: AsyncSession,
    chat_id: UUID,
    owner_id: UUID,
    message_id: UUID,
    error_code: str,
    *,
    attempt_started_at: datetime,
) -> Message | None:
    if not error_code.strip():
        raise ValueError("An error code is required")
    answer = await _pending_attempt(session, chat_id, owner_id, message_id, attempt_started_at)
    if answer is None:
        return None
    answer.updated_at = await session.scalar(select(func.clock_timestamp()))
    answer.status = "failed"
    answer.error_code = error_code
    await session.flush()
    return answer


async def list_answer_citations(
    session: AsyncSession, chat_id: UUID, owner_id: UUID, message_id: UUID
) -> list[AnswerCitation]:
    result = await session.scalars(
        select(AnswerCitation)
        .join(Message, Message.id == AnswerCitation.message_id)
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.id == message_id,
            Message.role == "assistant",
            Message.status == "completed",
            Chat.id == chat_id,
            Chat.owner_id == owner_id,
        )
        .order_by(AnswerCitation.position)
    )
    return list(result)
