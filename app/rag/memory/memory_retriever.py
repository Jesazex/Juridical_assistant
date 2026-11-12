from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import bindparam, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, ChatMemory
from app.rag.common.embeddings import validate_embedding


@dataclass(frozen=True)
class MemoryHit:
    """Context for query interpretation."""

    memory_id: UUID
    chat_id: UUID
    text: str
    score: float


async def search_chat_memory(
    session: AsyncSession,
    owner_id: UUID,
    chat_id: UUID,
    query: str,
    embedding: Sequence[float],
    *,
    limit: int = 5,
    candidate_limit: int = 20,
) -> list[MemoryHit]:
    if not query.strip() or not 1 <= limit <= candidate_limit:
        raise ValueError("Provide a nonblank query and valid result limits")

    memory = ChatMemory
    owned = (
        select(memory.id, memory.content)
        .join(Chat, Chat.id == memory.chat_id)
        .where(memory.chat_id == chat_id, Chat.owner_id == owner_id)
    )
    distance = memory.embedding.cosine_distance(validate_embedding(embedding))
    config = literal_column("'pg_catalog.russian'::regconfig")
    tsvector = func.to_tsvector(config, memory.content)
    tsquery = func.plainto_tsquery(config, bindparam("query", query))

    dense = await session.execute(
        owned.where(memory.embedding.is_not(None))
        .order_by(distance, memory.id)
        .limit(candidate_limit)
    )
    lexical = await session.execute(
        owned.where(tsvector.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(tsvector, tsquery).desc(), memory.id)
        .limit(candidate_limit)
    )

    scores: dict[UUID, float] = defaultdict(float)
    contents: dict[UUID, str] = {}
    for ranking in (dense, lexical):
        for rank, (item_id, content) in enumerate(ranking, start=1):
            scores[item_id] += 1 / (60 + rank)
            contents[item_id] = content

    ordered_ids = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    return [
        MemoryHit(item_id, chat_id, contents[item_id], scores[item_id])
        for item_id in ordered_ids[:limit]
    ]
