from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge.documents.id", ondelete="RESTRICT"),
    )
    version_label: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date | None] = mapped_column()
    effective_to: Mapped[date | None]
    source_file: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("version_label ~ '[^[:space:]]'"),
        CheckConstraint("source_file ~ '[^[:space:]]'"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'"),
        UniqueConstraint("document_id", "version_label", name="document_versions_label_unique"),
        CheckConstraint(
            "effective_from IS NULL OR effective_to IS NULL OR effective_from < effective_to",
            name="document_versions_valid_period",
        ),
        Index("document_versions_document_date_idx", document_id, effective_from.desc().nulls_last()),
        {"schema": "knowledge"},
    )
