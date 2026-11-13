"""Search the supplied documents and return traceable citation candidates."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Float, Text, bindparam, cast, func, literal_column, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, DocumentVersion
from app.rag.common.embeddings import validate_embedding

_RUSSIAN = literal_column("'pg_catalog.russian'::regconfig")


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    title: str
    section_path: str | None
    text: str
    page: int | None
    effective_from: date | None
    effective_to: date | None
    source_file: str
    url: str | None
    score: float


def _normalized_number(value):
    return func.regexp_replace(func.lower(value), r"[^[:alnum:]]+", "", "g")


def _matches_number(document_number: str):
    value = _normalized_number(document_number)
    return or_(
        _normalized_number(Document.document_number) == value,
        _normalized_number(Document.metadata_["base_document_number"].astext) == value,
    )


async def search_knowledge(
    session: AsyncSession, query: str, embedding: Sequence[float] | None = None, *,
    as_of: date | None = None, document_number: str | None = None,
    document_type: str | None = None, top_k: int = 5,
) -> list[KnowledgeHit]:
    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be between 1 and 50")
    if document_number is not None and not any(char.isalnum() for char in document_number):
        raise ValueError("document_number must contain a letter or digit")
    vector = validate_embedding(embedding) if embedding is not None else None
    if not query.strip() and vector is None:
        return []

    base = (
        select(
            DocumentChunk.id.label("chunk_id"), Document.id.label("document_id"),
            DocumentVersion.id.label("version_id"), Document.title,
            DocumentChunk.section_path, DocumentChunk.content.label("text"),
            DocumentChunk.page_from.label("page"), DocumentVersion.effective_from,
            DocumentVersion.effective_to,
            func.coalesce(DocumentVersion.source_file, Document.source_file).label("source_file"),
            Document.metadata_["url"].astext.label("url"),
        )
        .select_from(DocumentChunk)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
    )
    if as_of is not None:
        base = base.where(
            DocumentVersion.effective_from <= as_of,
            or_(DocumentVersion.effective_to.is_(None), DocumentVersion.effective_to > as_of),
        )
    if document_number is not None:
        base = base.where(_matches_number(document_number))
    if document_type is not None:
        base = base.where(Document.document_type == document_type)

    candidates = max(top_k * 3, 20)
    rankings = []
    if query.strip():
        indexed = func.to_tsvector(_RUSSIAN, DocumentChunk.content)
        terms = bindparam("knowledge_query", query, type_=Text())
        phrase = func.plainto_tsquery(_RUSSIAN, terms)
        # Form an OR over PostgreSQL-normalized words, using quote_literal around each lexeme.
        lexical = text("""
            (
                SELECT string_agg(quote_literal(lexeme), ' | ')::tsquery
                FROM unnest(tsvector_to_array(to_tsvector('pg_catalog.russian'::regconfig, :knowledge_query)))
                    AS tokens(lexeme)
            )
        """).bindparams(terms)
        rankings.append(
            (await session.execute(
                base.where(indexed.op("@@")(lexical))
                .order_by(indexed.op("@@")(phrase).desc(),
                          func.ts_rank_cd(indexed, lexical).desc(), DocumentChunk.id)
                .limit(candidates)
            )).mappings().all()
        )
    if vector is not None:
        distance = cast(DocumentChunk.embedding.cosine_distance(vector), Float())
        rankings.append(
            (await session.execute(
                base.where(DocumentChunk.embedding.is_not(None))
                .order_by(distance + 0, DocumentChunk.id)
                .limit(candidates)
            )).mappings().all()
        )

    by_id = {}
    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, row in enumerate(ranking, start=1):
            chunk_id = row["chunk_id"]
            by_id[chunk_id] = row
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (60 + rank)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [KnowledgeHit(**by_id[chunk_id], score=scores[chunk_id]) for chunk_id in ordered[:top_k]]
