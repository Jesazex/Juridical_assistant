"""Create missing tables for local development: python -m scripts.init_db."""
import asyncio

from app.db.database import Base, engine
from app.db import models  # noqa: F401 - registers mapped tables


async def main() -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
