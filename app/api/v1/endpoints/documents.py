from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import DBSession
from app.schemas.base import PaginationQuery
from app.schemas.document import DocumentContentResponse, DocumentDetailResponse, DocumentListResponse
from app.services import document_service

router = APIRouter()


@asynccontextmanager
async def document_transaction(db: AsyncSession) -> AsyncIterator[None]:
    try:
        async with db.begin():
            yield
    except document_service.DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except document_service.DocumentVersionNotFound as exc:
        raise HTTPException(status_code=404, detail="Document version not found") from exc


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    query: Annotated[PaginationQuery, Query()], db: DBSession,
) -> DocumentListResponse:
    """Каталог юридических документов с SQL-пагинацией."""
    async with document_transaction(db):
        return await document_service.list_documents(db, query.limit, query.offset)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: UUID, db: DBSession) -> DocumentDetailResponse:
    """Карточка документа, доступные редакции и однозначно выбранный текст."""
    async with document_transaction(db):
        return await document_service.get_document(db, document_id)


@router.get("/{document_id}/versions/{version_id}", response_model=DocumentContentResponse)
async def get_document_version(
    document_id: UUID, version_id: UUID, db: DBSession,
) -> DocumentContentResponse:
    """Полный текст именно запрошенной редакции, включая архивные редакции."""
    async with document_transaction(db):
        return await document_service.get_document_version(db, document_id, version_id)
