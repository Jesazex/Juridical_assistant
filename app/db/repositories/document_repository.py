from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, DocumentVersion


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    return await session.get(Document, document_id)


async def list_document_versions(
    session: AsyncSession, document_id: UUID
) -> list[DocumentVersion]:
    versions = await session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.effective_from.desc().nulls_last(), DocumentVersion.id)
    )
    return list(versions)


async def get_document_chunk(session: AsyncSession, chunk_id: UUID) -> DocumentChunk | None:
    return await session.get(DocumentChunk, chunk_id)
