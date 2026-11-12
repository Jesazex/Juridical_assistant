"""Application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from uuid import uuid4

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def anonymous_cookie(request: Request, call_next):
    anon_id = request.cookies.get("anon_id")
    needs_cookie = not anon_id or not anon_id.strip()
    request.state.anon_id = str(uuid4()) if needs_cookie else anon_id
    response = await call_next(request)
    if needs_cookie:
        response.set_cookie(
            "anon_id", request.state.anon_id,
            max_age=30 * 24 * 60 * 60, httponly=True,
            samesite="lax", path="/", secure=settings.anon_cookie_secure,
        )
    return response


app.include_router(api_router, prefix=settings.api_v1_prefix)

