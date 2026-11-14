from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.base import PaginatedResponse


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    document_type: str
    document_number: str | None
    source_file: str
    metadata: dict[str, Any]
    created_at: datetime
    group: Literal["company", "law"] | None = None


class DocumentListResponse(PaginatedResponse[DocumentResponse]):
    pass


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    version_label: str
    effective_from: date | None
    effective_to: date | None
    source_file: str | None
    created_at: datetime


class DocumentDetailResponse(DocumentResponse):
    versions: list[DocumentVersionResponse]
    selected_version_id: UUID | None
    selection_reason: Literal["current", "single_undated", "ambiguous", "no_current", "no_versions"]
    text: str | None


class DocumentContentResponse(DocumentResponse):
    version_id: UUID
    version_label: str
    effective_from: date | None
    effective_to: date | None
    version_created_at: datetime
    text: str
