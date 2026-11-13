"""Import the UTF-8 text corpus supplied by the PSB organizers."""

import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, DocumentVersion
from app.rag.common.embeddings import embed_texts
from app.rag.knowledge.chunker import SourceChunk, chunk_text

_COMPANY = "документы компании"
_LAWS = "законы"
_REGULATION = "РЕГЛАМЕНТ СОГЛАСОВАНИЯ ДОГОВОРОВ ООО «МЕРИДИАН»"
_EDITION = re.compile(r"Редакция от (\d{2}\.\d{2}\.\d{4})")
_ENDING = re.compile(r"УТРАТИЛА СИЛУ с (\d{2}\.\d{2}\.\d{4})")
_NUMBER = re.compile(r"№\s*([\w/-]+)")
_LAW_FILENAME = re.compile(r"(?P<law>.+)_ст(?P<article>\d+(?:\.\d+)*)_действующая$")

# Confirmed in the corpus. A version date is distinct from a conditional clause's start.
_COMPANY_PERIODS: dict[str, tuple[date | None, date | None]] = {
    "П-17/2024": (date(2024, 2, 12), date(2027, 1, 1)),
    "К-12": (date(2025, 4, 21), None),
}


@dataclass(frozen=True)
class SourceVersion:
    key: str
    title: str
    kind: str
    number: str | None
    filename: str
    metadata: dict[str, str]
    label: str
    effective_from: date | None
    effective_to: date | None
    digest: str
    chunks: list[SourceChunk]


@dataclass(frozen=True)
class ImportSummary:
    documents: int
    versions: int
    chunks: int
    embeddings_added: int


def _parse_date(value: str) -> date:
    day, month, year = value.split(".")
    return date(int(year), int(month), int(day))


def _source_version(path: Path) -> SourceVersion:
    raw = path.read_bytes()
    value = raw.decode("utf-8-sig")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Empty document: {path.name}")
    category, _, caption = path.stem.partition("__")
    metadata = {"category": category} if caption else {}
    begin = end = None
    number = article = None
    title = lines[0]
    key = path.name
    label = "Предоставленная редакция"
    kind = "документ"
    if category == _LAWS:
        kind = "закон"
        label = "Действующая редакция по данным корпуса"
        title = title.removeprefix("Источник: ")
        match = _LAW_FILENAME.fullmatch(caption)
        if match:
            article = f"Статья {match['article']}"
            number = f"{match['law']} ст. {match['article']}"
        provenance = (
            ("url", "URL: "),
            ("exported_at", "Дата выгрузки: "),
        )
        for name, prefix in provenance:
            item = next((line for line in lines[:3] if line.startswith(prefix)), None)
            if item is not None:
                metadata[name] = item.removeprefix(prefix)
        value = "\n".join(
            line for line in value.splitlines()
            if not line.startswith(("Источник: ", "URL: ", "Дата выгрузки: "))
        )
    elif category == _COMPANY:
        if caption.startswith("Регламент согласования договоров ред "):
            edition = _EDITION.search(value)
            if edition is None:
                raise ValueError(f"No edition date in {path.name}")
            title, kind, key = _REGULATION, "регламент", _REGULATION
            label = edition[0]
            begin = _parse_date(edition[1])
            ending = _ENDING.search(value)
            end = _parse_date(ending[1]) if ending else None
        elif caption.startswith("Договор"):
            kind = "договор"
            match = _NUMBER.search(title)
            number = match[1] if match else None
            begin, end = _COMPANY_PERIODS.get(number, (None, None))
        elif caption.startswith("Доп соглашение"):
            kind = "дополнительное соглашение"
            match = _NUMBER.search(title)
            number = match[1] if match else None
            base_number = _NUMBER.search(lines[1])
            if base_number:
                metadata["base_document_number"] = base_number[1]
                title = f"{title} {lines[1]}"
            if "3 сентября 2024 г." in lines[2] and "вступает в силу с даты подписания" in value:
                begin = date(2024, 9, 3)
        elif caption.startswith("Письмо комплаенс-службы"):
            kind = "письмо"
            title = next(line for line in lines if line.startswith("О санкционной проверке"))
            match = _NUMBER.search(value)
            number = match[1] if match else None
            begin, end = _COMPANY_PERIODS.get(number, (None, None))
        elif caption.startswith("Служебная записка"):
            kind = "служебная записка"
            title = next(line for line in lines if line.startswith("СЛУЖЕБНАЯ ЗАПИСКА"))
            match = _NUMBER.search(title)
            number = match[1] if match else None
    chunks = chunk_text(value, article=article)
    if not chunks:
        raise ValueError(f"No indexable text in {path.name}")
    return SourceVersion(
        key, title, kind, number, path.name, metadata, label, begin, end,
        sha256(raw).hexdigest(), chunks,
    )


async def import_corpus(
    session: AsyncSession, directory: Path, *, with_embeddings: bool = False,
) -> ImportSummary:
    sources = [_source_version(path) for path in sorted(directory.glob("*.txt")) if path.is_file()]
    if not sources:
        raise ValueError(f"No TXT documents in {directory}")
    # All imports take the same transaction lock, including idempotency checks.
    await session.execute(text("SELECT pg_advisory_xact_lock(469935273, 1)"))
    documents: dict[str, Document] = {}
    chunks: list[DocumentChunk] = []
    for source in sorted(sources, key=lambda src: (src.key, src.effective_to is not None)):
        if source.key not in documents:
            document_id = uuid5(NAMESPACE_URL, f"psb:knowledge:document:{source.key}")
            document = await session.get(Document, document_id)
            if document is None:
                document = Document(
                    id=document_id, title=source.title, document_type=source.kind,
                    document_number=source.number, source_file=source.filename,
                    metadata_=source.metadata,
                )
                session.add(document)
                await session.flush()
            documents[source.key] = document
        document = documents[source.key]
        version = await session.scalar(select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_label == source.label,
        ))
        if version is not None and version.content_hash != source.digest:
            raise ValueError(f"Existing version has different content: {source.filename}")
        if version is None:
            version = DocumentVersion(
                document_id=document.id, version_label=source.label, source_file=source.filename,
                effective_from=source.effective_from, effective_to=source.effective_to,
                content_hash=source.digest,
            )
            session.add(version)
            await session.flush()
        existing = list(await session.scalars(
            select(DocumentChunk).where(DocumentChunk.version_id == version.id)
            .order_by(DocumentChunk.chunk_index)
        ))
        if existing:
            if len(existing) != len(source.chunks) or any(
                (chunk.chunk_index, chunk.section_path, chunk.content)
                != (index, expected.section_path, expected.content)
                for index, (chunk, expected) in enumerate(zip(existing, source.chunks))
            ):
                raise ValueError(f"Stored chunks differ from source: {source.filename}")
        else:
            existing = [
                DocumentChunk(
                    version_id=version.id, chunk_index=index, section_path=chunk.section_path,
                    content=chunk.content,
                )
                for index, chunk in enumerate(source.chunks)
            ]
            session.add_all(existing)
        chunks.extend(existing)
    pending = [chunk for chunk in chunks if chunk.embedding is None] if with_embeddings else []
    if pending:
        vectors = await embed_texts([
            "\n".join(filter(None, [chunk.section_path, chunk.content])) for chunk in pending
        ])
        for chunk, vector in zip(pending, vectors, strict=True):
            chunk.embedding = vector
    await session.flush()
    return ImportSummary(len(documents), len(sources), len(chunks), len(pending))
