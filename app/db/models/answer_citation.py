from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnswerCitation(Base):
    __tablename__ = "answer_citations"
    __table_args__ = (
        CheckConstraint("position >= 0"),
        CheckConstraint("document_title_snapshot ~ '[^[:space:]]'"),
        CheckConstraint("page_snapshot > 0"),
        UniqueConstraint("message_id", "position", name="answer_citation_position_unique"),
        Index(
            "answer_citations_chunk_idx",
            "chunk_id",
            postgresql_where=text("chunk_id IS NOT NULL"),
        ),
        {"schema": "chat"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    message_id: Mapped[UUID] = mapped_column(ForeignKey("chat.messages.id", ondelete="CASCADE"))
    chunk_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge.document_chunks.id", ondelete="SET NULL"),
    )
    position: Mapped[int]
    document_id_snapshot: Mapped[str | None] = mapped_column(Text)
    document_title_snapshot: Mapped[str] = mapped_column(Text)
    section_snapshot: Mapped[str | None] = mapped_column(Text)
    page_snapshot: Mapped[int | None]
    excerpt_snapshot: Mapped[str | None] = mapped_column(Text)
    url_snapshot: Mapped[str | None] = mapped_column(Text)
