from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("title ~ '[^[:space:]]'"),
        CheckConstraint("document_type ~ '[^[:space:]]'"),
        CheckConstraint("source_file ~ '[^[:space:]]'"),
        CheckConstraint("jsonb_typeof(metadata) = 'object'"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    title: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(Text)
    document_number: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
