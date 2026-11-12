from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat.anonymous_users.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(Text, server_default="Новый чат")
    is_title_custom: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("title ~ '[^[:space:]]'"),
        Index("chats_owner_updated_idx", owner_id, updated_at.desc()),
        {"schema": "chat"},
    )
