from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("chat_id", "id", name="messages_chat_id_id_unique"),
        ForeignKeyConstraint(
            ("chat_id", "reply_to_message_id"),
            ("chat.messages.chat_id", "chat.messages.id"),
            name="messages_reply_same_chat_fk",
            ondelete="SET NULL (reply_to_message_id)",
        ),
        CheckConstraint("role IN ('user', 'assistant')"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')"),
        CheckConstraint(
            """(role = 'user' AND status IS NULL AND reply_to_message_id IS NULL
                    AND content ~ '[^[:space:]]')
               OR (role = 'assistant' AND status IS NOT NULL
                    AND (status <> 'completed' OR content ~ '[^[:space:]]'))""",
            name="message_role_status_chk",
        ),
        CheckConstraint(
            "error_code IS NULL OR status IS NOT DISTINCT FROM 'failed'",
            name="messages_error_status_chk",
        ),
        Index("messages_chat_chronology_idx", "chat_id", "created_at", "id"),
        Index(
            "messages_reply_idx",
            "reply_to_message_id",
            postgresql_where=text("reply_to_message_id IS NOT NULL"),
        ),
        Index(
            "messages_one_answer_per_question_idx",
            "reply_to_message_id",
            unique=True,
            postgresql_where=text("role = 'assistant' AND reply_to_message_id IS NOT NULL"),
        ),
        {"schema": "chat"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("chat.chats.id", ondelete="CASCADE"))
    reply_to_message_id: Mapped[UUID | None]
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
