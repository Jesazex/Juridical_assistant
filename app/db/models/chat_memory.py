from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatMemory(Base):
    __tablename__ = "chat_memory"
    __table_args__ = (
        ForeignKeyConstraint(
            ("chat_id", "source_message_id"),
            ("chat.messages.chat_id", "chat.messages.id"),
            name="chat_memory_source_same_chat_fk",
            ondelete="SET NULL (source_message_id)",
        ),
        CheckConstraint("memory_type IN ('context', 'summary')"),
        CheckConstraint("content ~ '[^[:space:]]'"),
        CheckConstraint("public.vector_norm(embedding) > 0"),
        Index("chat_memory_chat_id_idx", "chat_id"),
        Index(
            "chat_memory_source_idx",
            "source_message_id",
            postgresql_where=text("source_message_id IS NOT NULL"),
        ),
        Index(
            "chat_memory_fts_ru_idx",
            text("to_tsvector('pg_catalog.russian'::regconfig, content)"),
            postgresql_using="gin",
        ),
        {"schema": "chat"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("chat.chats.id", ondelete="CASCADE"))
    source_message_id: Mapped[UUID | None]
    memory_type: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
