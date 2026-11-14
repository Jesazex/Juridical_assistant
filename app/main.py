"""Application entry point."""
from contextlib import asynccontextmanager
from os import environ
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.db.session import create_database_engine, create_session_factory

DEFAULT_CORS_ORIGINS = {
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


@asynccontextmanager
async def lifespan(application: FastAPI):
    engine = create_database_engine()
    application.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def configured_origins() -> set[str]:
    value = environ.get("PSB_CORS_ORIGINS", "").strip()
    # Production задаёт полный список через окружение, заменяя локальные defaults.
    origins = {
        origin.strip().rstrip("/")
        for origin in value.split(",")
        if origin.strip()
    } if value else DEFAULT_CORS_ORIGINS.copy()
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
        ):
            raise ValueError("PSB_CORS_ORIGINS must contain explicit HTTP(S) origins")
    return origins


trusted_origins = configured_origins()

app = FastAPI(title="Juridical Assistant", lifespan=lifespan)
app.state.cookie_secure = environ.get("PSB_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


@app.middleware("http")
async def check_write_origin(request: Request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        # Схема уже обработана Uvicorn только для доверенного proxy peer.
        # Самостоятельно читать X-Forwarded-* здесь нельзя.
        request_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin is not None:
            allowed = origin in trusted_origins or origin.lower() == request_origin.lower()
        else:
            allowed = request.headers.get("sec-fetch-site") not in {"cross-site", "same-site"}
        if not allowed:
            return JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)

    response = await call_next(request)
    if request.url.path.startswith("/api/v1/chats"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # HTTP input can contain tokens or personal data, so strip echoed values.
    detail = [
        {key: error[key] for key in ("loc", "msg", "type")}
        for error in exc.errors()
    ]
    return JSONResponse({"detail": detail}, status_code=422)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(trusted_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(api_router, prefix="/api/v1")
