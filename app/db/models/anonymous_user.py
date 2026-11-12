from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnonymousUser(Base):
    __tablename__ = "anonymous_users"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'"),
        {"schema": "chat"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
