"""Application entry point."""
from fastapi import FastAPI
#импорт настроек из comfig
from app.core.config import get_settings

from app.api.v1.router import api_router

settings = get_settings()

app = FastAPI(
    title = settings.app_name,
    version = settings.app_version,
    debug = settings.debug
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)

