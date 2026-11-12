"""Run from the project root with the migration account. All fixtures are rolled back."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnswerCitation, ChatMemory, Document, DocumentChunk, DocumentVersion, Message
from app.db.repositories.chat_repository import (
    create_chat,
    delete_owned_chat,
    get_owned_chat,
    upsert_anonymous_user,
)
from app.db.repositories.memory_repository import save_chat_memory
from app.db.repositories.message_repository import (
    complete_answer,
    create_pending_answer,
    fail_answer,
    list_answer_citations,
    list_owned_messages,
    save_user_message,
)
from app.db.session import create_database_engine, create_session_factory
from app.rag.memory.memory_retriever import search_chat_memory


async def check_database(session: AsyncSession) -> None:
    assert await session.scalar(text("SELECT current_database()")) == "psb_knowledge"
    assert await session.scalar(text("""
        SELECT count(*) FROM pg_tables WHERE schemaname IN ('knowledge', 'chat')
    """)) == 8

    vector = [1.0] + [0.0] * 1023
    document = Document(title="Тестовый договор", document_type="Договор", source_file="fixture.txt")
    session.add(document)
    await session.flush()
    version = DocumentVersion(document_id=document.id, version_label="Тест", content_hash="a" * 64)
    session.add(version)
    await session.flush()
    chunk = DocumentChunk(
        version_id=version.id,
        chunk_index=0,
        section_path="Пункт 4.2",
        content="Тестовое условие согласования договора.",
        embedding=vector,
    )
    session.add(chunk)
    await session.flush()

    await session.execute(text("SET LOCAL ROLE psb_knowledge_reader"))
    assert await session.scalar(text("SELECT NOT has_schema_privilege('chat', 'USAGE')"))
    assert await session.scalar(text("""
        SELECT NOT has_table_privilege(c.oid, 'SELECT')
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'chat' AND c.relname = 'messages'
    """))
    await session.execute(text("SET LOCAL ROLE psb_chat_backend"))
    assert await session.scalar(
        text("SELECT NOT has_table_privilege('knowledge.documents', 'INSERT')")
    )

    owner_a = await upsert_anonymous_user(session, uuid4().hex + uuid4().hex)
    owner_b = await upsert_anonymous_user(session, uuid4().hex + uuid4().hex)
    chat_a = await create_chat(session, owner_a.id)
    other_a = await create_chat(session, owner_a.id)
    chat_b = await create_chat(session, owner_b.id)
    other_b = await create_chat(session, owner_b.id)
    assert await get_owned_chat(session, other_a.id, owner_b.id) is None
    assert await list_owned_messages(session, chat_a.id, owner_b.id) is None
    assert not await delete_owned_chat(session, chat_a.id, owner_b.id)

    question = await save_user_message(session, chat_a.id, owner_a.id, "Как согласовать договор?")
    assert chat_a.title == "Как согласовать договор?"
    assert await create_pending_answer(session, other_a.id, owner_a.id, question.id) is None
    try:
        async with session.begin_nested():
            session.add(Message(
                chat_id=other_a.id,
                reply_to_message_id=question.id,
                role="assistant",
                status="pending",
            ))
            await session.flush()
    except IntegrityError as error:
        assert error.orig.sqlstate == "23503"
    else:
        raise AssertionError("PostgreSQL accepted a reply to a message in another chat")

    attempt = await create_pending_answer(session, chat_a.id, owner_a.id, question.id)
    duplicate = await create_pending_answer(session, chat_a.id, owner_a.id, question.id)
    assert duplicate.message.id == attempt.message.id and duplicate.started_at is None
    assert await fail_answer(
        session, chat_a.id, owner_a.id, attempt.message.id, "provider_unavailable",
        attempt_started_at=attempt.started_at,
    )
    retry = await create_pending_answer(session, chat_a.id, owner_a.id, question.id)
    assert retry.message.id == attempt.message.id and retry.started_at != attempt.started_at
    assert await fail_answer(
        session, chat_a.id, owner_a.id, attempt.message.id, "stale_attempt",
        attempt_started_at=attempt.started_at,
    ) is None
    answer = await complete_answer(
        session, chat_a.id, owner_a.id, retry.message.id, "См. пункт 4.2.",
        attempt_started_at=retry.started_at, citations=[chunk.id],
    )
    citations = await list_answer_citations(session, chat_a.id, owner_a.id, answer.id)
    assert len(citations) == 1 and citations[0].chunk_id == chunk.id
    assert citations[0].section_snapshot == chunk.section_path and citations[0].page_snapshot is None
    assert not await list_answer_citations(session, chat_a.id, owner_b.id, answer.id)

    context = await save_chat_memory(
        session, owner_a.id, chat_a.id, "Пользователь спрашивает о договоре",
        source_message_id=question.id, embedding=[-x for x in vector],
    )
    lexical_only = await save_chat_memory(
        session, owner_a.id, chat_a.id, "Контрагент указан в договоре"
    )
    await save_chat_memory(session, owner_b.id, chat_b.id, "Чужой договор", embedding=vector)
    hits = await search_chat_memory(session, owner_a.id, chat_a.id, "договор", vector)
    assert [hit.memory_id for hit in hits] == [context.id, lexical_only.id]
    assert not await search_chat_memory(session, owner_b.id, chat_a.id, "договор", vector)

    assert await delete_owned_chat(session, chat_a.id, owner_a.id)
    for model, column, value in (
        (Message, Message.chat_id, chat_a.id),
        (ChatMemory, ChatMemory.chat_id, chat_a.id),
        (AnswerCitation, AnswerCitation.message_id, answer.id),
    ):
        assert await session.scalar(select(func.count()).select_from(model).where(column == value)) == 0
    assert not await search_chat_memory(session, owner_a.id, chat_a.id, "договор", vector)
    assert await get_owned_chat(session, other_a.id, owner_a.id)
    assert await get_owned_chat(session, chat_b.id, owner_b.id)
    assert await get_owned_chat(session, other_b.id, owner_b.id)
    assert await session.scalar(select(DocumentChunk.id).where(DocumentChunk.id == chunk.id)) == chunk.id


async def main() -> None:
    engine = create_database_engine()
    try:
        async with create_session_factory(engine)() as session:
            try:
                await check_database(session)
            finally:
                await session.rollback()
        print("Verified eight tables, repository operations, ACLs, RAG memory, and cascade deletion.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
