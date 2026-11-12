from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0"),
        CheckConstraint("section_path ~ '[^[:space:]]'"),
        CheckConstraint("page_from > 0"),
        CheckConstraint("content ~ '[^[:space:]]'"),
        CheckConstraint("public.vector_norm(embedding) > 0"),
        UniqueConstraint("version_id", "chunk_index", name="document_chunks_index_unique"),
        CheckConstraint(
            "page_to IS NULL OR (page_from IS NOT NULL AND page_to >= page_from)",
            name="document_chunks_valid_pages",
        ),
        Index(
            "document_chunks_content_fts_idx",
            text("to_tsvector('pg_catalog.russian'::regconfig, content)"),
            postgresql_using="gin",
        ),
        Index(
            "document_chunks_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "public.vector_cosine_ops"},
        ),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge.document_versions.id", ondelete="RESTRICT"),
    )
    chunk_index: Mapped[int]
    section_path: Mapped[str | None] = mapped_column(Text)
    page_from: Mapped[int | None]
    page_to: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
