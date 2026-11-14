from collections.abc import Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.models import AnswerCitation, Message
from app.schemas.base import BaseRequest, PaginatedResponse, PaginationQuery, validate_text


class MessageCreate(BaseRequest):
    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: object) -> object:
        return validate_text(value)


class MessageListQuery(PaginationQuery):
    limit: int = Field(default=50, ge=1, le=100)


class MessageSource(BaseModel):
    document_id: str | None
    document_title: str
    chunk_id: UUID | None
    version_id: UUID | None = None
    page: int | None
    excerpt: str | None
    url: str | None
    section: str | None

    @classmethod
    def from_citation(cls, citation: AnswerCitation, version_id: UUID | None = None) -> "MessageSource":
        return cls(
            document_id=citation.document_id_snapshot,
            document_title=citation.document_title_snapshot,
            chunk_id=citation.chunk_id,
            version_id=version_id,
            page=citation.page_snapshot,
            excerpt=citation.excerpt_snapshot,
            url=citation.url_snapshot,
            section=citation.section_snapshot,
        )


class MessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    reply_to_message_id: UUID | None
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "completed", "failed"]
    sources: list[MessageSource]
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_message(
        cls, message: Message, citations: Sequence[AnswerCitation | MessageSource] = ()
    ) -> "MessageResponse":
        return cls(
            id=message.id,
            chat_id=message.chat_id,
            reply_to_message_id=message.reply_to_message_id,
            role=message.role,
            content=message.content,
            status=message.status or "completed",
            sources=[
                citation if isinstance(citation, MessageSource) else MessageSource.from_citation(citation)
                for citation in citations
            ],
            error_code=message.error_code,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )


class MessageListResponse(PaginatedResponse[MessageResponse]):
    pass


class MessageExchangeResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
