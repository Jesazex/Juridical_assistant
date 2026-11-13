"""Create missing tables for local development: python -m scripts.init_db."""
import asyncio
import argparse

from sqlalchemy import inspect, text

from app.db.database import Base, engine
from app.db import models  # noqa: F401 - registers mapped tables


def initialize(connection, upgrade_messages: bool = False) -> None:
    """Explicit, idempotent local upgrade; never run during app startup."""
    inspector = inspect(connection)
    if inspector.has_table("chats"):
        columns = {column["name"] for column in inspector.get_columns("chats")}
        if "title_is_manual" not in columns:
            if not upgrade_messages:
                raise RuntimeError("Existing chats schema needs --upgrade-messages")
            connection.execute(text(
                "ALTER TABLE chats ADD COLUMN title_is_manual BOOLEAN NOT NULL DEFAULT false"
            ))
            # Historical titles have no provenance; preserve them rather than overwrite.
            connection.execute(text("UPDATE chats SET title_is_manual = true"))
    Base.metadata.create_all(connection)


async def main(upgrade_messages: bool = False) -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(initialize, upgrade_messages)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upgrade-messages", action="store_true")
    asyncio.run(main(parser.parse_args().upgrade_messages))
