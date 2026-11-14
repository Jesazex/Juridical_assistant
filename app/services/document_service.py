"""Service задаёт правила выбора редакции; SQL и ORM остаются в Repository."""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import document_repository as repository
from app.schemas.document import (
    DocumentContentResponse, DocumentDetailResponse, DocumentListResponse,
    DocumentResponse, DocumentVersionResponse,
)


class DocumentNotFound(Exception):
    """Документ не найден."""


class DocumentVersionNotFound(Exception):
    """Редакция не найдена в указанном документе."""


def _with_group(document: DocumentResponse) -> DocumentResponse:
    category = document.metadata.get("category")
    group = "law" if category == "законы" or document.document_type in {"law", "закон"} else "company"
    return document.model_copy(update={"group": group})


async def _document(session: AsyncSession, document_id: UUID) -> DocumentResponse:
    document = await repository.get_document(session, document_id)
    if document is None:
        raise DocumentNotFound
    return _with_group(document)


async def list_documents(session: AsyncSession, limit: int = 20, offset: int = 0) -> DocumentListResponse:
    documents = await repository.list_documents(session, limit, offset)
    return DocumentListResponse(
        items=[_with_group(document) for document in documents],
        total=await repository.count_documents(session), limit=limit, offset=offset,
    )


def select_version(versions: list[DocumentVersionResponse], today: date):
    # Период действия [effective_from, effective_to), как в существующем retriever.
    # Неизвестное начало не доказывает актуальность и может сделать выбор неоднозначным.
    candidates = [version for version in versions if (
        (version.effective_from is None or version.effective_from <= today)
        and (version.effective_to is None or today < version.effective_to)
    )]
    if len(candidates) == 1 and candidates[0].effective_from is not None:
        return candidates[0], "current"
    # Единственная недатированная редакция доступна, но не объявляется действующей.
    if len(versions) == 1 and versions[0].effective_from is None and versions[0].effective_to is None:
        return versions[0], "single_undated"
    return None, "no_versions" if not versions else "ambiguous" if candidates else "no_current"


async def get_document(session: AsyncSession, document_id: UUID) -> DocumentDetailResponse:
    document = await _document(session, document_id)
    versions = await repository.list_document_versions(session, document_id)
    selected, reason = select_version(versions, datetime.now(timezone.utc).date())
    text = await repository.get_version_text(session, document_id, selected.id) if selected else None
    return DocumentDetailResponse(
        **document.model_dump(), versions=versions,
        selected_version_id=selected.id if selected else None, selection_reason=reason, text=text,
    )


async def get_document_version(
    session: AsyncSession, document_id: UUID, version_id: UUID,
) -> DocumentContentResponse:
    document = await _document(session, document_id)
    version = await repository.get_document_version(session, document_id, version_id)
    if version is None:
        raise DocumentVersionNotFound
    data = document.model_dump()
    data["source_file"] = version.source_file or document.source_file
    return DocumentContentResponse(
        **data, version_id=version.id, version_label=version.version_label,
        effective_from=version.effective_from, effective_to=version.effective_to,
        version_created_at=version.created_at,
        text=await repository.get_version_text(session, document_id, version_id),
    )
