"""Split corpus text at numbered legal provisions and source headings."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

_CLAUSE = re.compile(r"^[«\s]*(\d+(?:\.\d+)*)\.\s+")
_ARTICLE = re.compile(r"^(Статья\s+\d+(?:\.\d+)*)\.\s", re.I)
_APPENDIX = re.compile(r"^(Приложение\s+\d+)\.\s", re.I)
_CONTROL_LINE = re.compile(r"^ВНИМАНИЕ ДЛЯ ИИ-АССИСТЕНТА\s*:", re.I)
_MAX_CHARS = 2200


@dataclass(frozen=True)
class SourceChunk:
    section_path: str | None
    content: str


def _parts(value: str) -> Iterator[str]:
    while len(value) > _MAX_CHARS:
        end = value.rfind("\n", _MAX_CHARS // 2, _MAX_CHARS)
        if end < 0:
            end = value.rfind(" ", _MAX_CHARS // 2, _MAX_CHARS)
        if end < 0:
            end = _MAX_CHARS
        yield value[:end].rstrip()
        value = value[end:].lstrip()
    if value:
        yield value


def chunk_text(text: str, *, article: str | None = None) -> list[SourceChunk]:
    blocks: list[SourceChunk] = []
    section = article
    path = section
    lines: list[str] = []

    def append_block() -> None:
        blocks.extend(SourceChunk(path, part) for part in _parts("\n".join(lines).strip()))
        lines.clear()

    for line in text.splitlines():
        line = line.strip()
        if _CONTROL_LINE.match(line):
            continue
        heading = _ARTICLE.match(line) or _APPENDIX.match(line)
        clause = _CLAUSE.match(line)
        if heading:
            append_block()
            section = path = heading[1]
        elif clause:
            append_block()
            number = clause[1]
            if article is None and "." not in number:
                section = line
                path = section
            else:
                path = f"{section} / п. {number}" if section else f"п. {number}"
        lines.append(line)
    append_block()
    return blocks
