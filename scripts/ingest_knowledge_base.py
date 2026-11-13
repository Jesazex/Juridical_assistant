"""Index the organizer's UTF-8 documents from the PSB project directory."""

import argparse
import asyncio
from pathlib import Path

from app.db.session import create_database_engine, create_session_factory
from app.rag.knowledge.ingestion import import_corpus


async def run(directory: Path, with_embeddings: bool) -> None:
    engine = create_database_engine()
    try:
        async with create_session_factory(engine).begin() as session:
            summary = await import_corpus(session, directory, with_embeddings=with_embeddings)
    finally:
        await engine.dispose()
    print(
        f"Documents: {summary.documents}, versions: {summary.versions}, "
        f"chunks: {summary.chunks}, embeddings added: {summary.embeddings_added}"
    )


def main() -> None:
    default_directory = Path(__file__).resolve().parents[1] / "knowledge_base" / "source_documents"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=default_directory)
    parser.add_argument("--embed", action="store_true", help="Generate missing BGE-M3 embeddings")
    options = parser.parse_args()
    asyncio.run(run(options.directory, options.embed))


if __name__ == "__main__":
    main()
