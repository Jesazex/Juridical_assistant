"""Application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI

#импорт настроек из comfig
from app.core.config import get_settings

from app.api.v1.router import api_router
from app.db.database import close_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Освобождает пул БД при завершении приложения, в том числе после ошибки."""
    try:
        yield
    finally:
        await close_db()


app = FastAPI(
    title = settings.app_name,
    version = settings.app_version,
    debug = settings.debug,
    lifespan=lifespan,
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)

