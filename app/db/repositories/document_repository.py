"""Repository выполняет SQL и возвращает данные документов без embeddings."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.db.models import Document, DocumentChunk, DocumentVersion
from app.schemas.document import DocumentResponse, DocumentVersionResponse


def _document_select():
    return select(
        Document.id, Document.title, Document.document_type, Document.document_number,
        Document.source_file, Document.metadata_.label("metadata"), Document.created_at,
    )


def _version_select():
    return select(
        DocumentVersion.id, DocumentVersion.document_id, DocumentVersion.version_label,
        DocumentVersion.effective_from, DocumentVersion.effective_to,
        DocumentVersion.source_file, DocumentVersion.created_at,
    )


async def list_documents(
    session: AsyncSession, limit: int = 20, offset: int = 0,
) -> list[DocumentResponse]:
    rows = await session.execute(
        _document_select().order_by(Document.title, Document.id).limit(limit).offset(offset),
    )
    return [DocumentResponse.model_validate(row) for row in rows.mappings()]


async def count_documents(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Document))


async def get_document(session: AsyncSession, document_id: UUID) -> DocumentResponse | None:
    result = await session.execute(_document_select().where(Document.id == document_id))
    row = result.mappings().one_or_none()
    return DocumentResponse.model_validate(row) if row is not None else None


async def list_document_versions(
    session: AsyncSession, document_id: UUID
) -> list[DocumentVersionResponse]:
    versions = await session.execute(
        _version_select()
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.effective_from.desc().nulls_last(), DocumentVersion.id)
    )
    return [DocumentVersionResponse.model_validate(row) for row in versions.mappings()]


async def get_document_version(
    session: AsyncSession, document_id: UUID, version_id: UUID,
) -> DocumentVersionResponse | None:
    # Редакция всегда проверяется вместе с документом: чужой UUID не подойдёт.
    result = await session.execute(_version_select().where(
        DocumentVersion.id == version_id, DocumentVersion.document_id == document_id,
    ))
    row = result.mappings().one_or_none()
    return DocumentVersionResponse.model_validate(row) if row is not None else None


async def get_document_chunk(session: AsyncSession, chunk_id: UUID) -> DocumentChunk | None:
    return await session.get(DocumentChunk, chunk_id)


async def list_version_chunks(session: AsyncSession, version_id: UUID) -> list[DocumentChunk]:
    chunks = await session.scalars(
        select(DocumentChunk)
        .options(defer(DocumentChunk.embedding, raiseload=True))
        .where(DocumentChunk.version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(chunks)


def merge_chunk_texts(contents: Sequence[str]) -> str:
    """Склеить chunks, убрав точные перекрытия строк или длинных границ слов.

    Текущий knowledge.chunker не делает overlap: обычные блоки разделяем пустой
    строкой. Без смещений исходного текста восстановление пробелов не гарантируется.
    Короткие совпадения слов не удаляем, чтобы не терять повторяющиеся формулировки.
    """
    parts: list[str] = []
    previous = ""
    for content in contents:
        if not previous:
            parts.append(content)
            previous = content
            continue
        # Префикс-функция находит overlap за линейное время, без квадратичного перебора.
        sequence = list(content) + [None] + list(previous[-len(content):])
        prefix = [0] * len(sequence)
        for index in range(1, len(sequence)):
            length = prefix[index - 1]
            while length and sequence[index] != sequence[length]:
                length = prefix[length - 1]
            if sequence[index] == sequence[length]:
                length += 1
            prefix[index] = length
        overlap = prefix[-1]
        while overlap:
            start = len(previous) - overlap
            line_boundary = (start == 0 or previous[start - 1] == "\n") and (
                overlap == len(content) or content[overlap] == "\n"
            )
            word_boundary = overlap >= 80 and (
                start == 0 or previous[start - 1].isspace()
            ) and (overlap == len(content) or content[overlap].isspace() or content[overlap - 1].isspace())
            if line_boundary or word_boundary:
                break
            overlap = prefix[overlap - 1]
        parts.append(content[overlap:] if overlap else "\n\n" + content)
        previous = content
    return "".join(parts)


async def get_version_text(session: AsyncSession, document_id: UUID, version_id: UUID) -> str:
    # Читаем только текст одной редакции, без векторов и остальных документов базы.
    contents = await session.scalars(
        select(DocumentChunk.content)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.id == version_id)
        .order_by(DocumentChunk.chunk_index),
    )
    return merge_chunk_texts(list(contents))
