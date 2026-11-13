# Juridical Assistant

FastAPI application with an asynchronous chat API. LLM, RAG and message modules
remain placeholders.

## Local development (Python 3.13)

Install `requirements-dev.txt`, then configure `.env` using `.env.example`.
Initialize missing tables with `python -m scripts.init_db` and start the app with
`uvicorn app.main:app --reload`. Table creation is explicit; application startup
never changes the database schema. `create_all` does not migrate existing tables.

`DATABASE_URL` defaults to `sqlite+aiosqlite:///./juridical_assistant.db`.
For PostgreSQL use `postgresql+asyncpg://user:password@localhost/database`.
Before production deployment, add versioned migrations in `migrations/`.

## Chats API

Every HTTP request reuses a nonblank anon_id cookie or creates a UUID cookie.
The browser retains it for 30 days (HttpOnly, SameSite=Lax, Path=/).
Set ANON_COOKIE_SECURE=false for local HTTP and true for production HTTPS.
AnonId remains a FastAPI dependency; owner_id filtering is unchanged.

For a separate frontend origin, set CORS_ORIGINS to a JSON list of explicit
origins, e.g. ["http://localhost:5173"], and use fetch credentials: "include"
(or Axios withCredentials: true). Credentials are enabled; wildcards are rejected.
Use the same hostname locally. SameSite=Lax supports same-site origins with
different ports; unrelated frontend/backend sites need a same-site proxy deployment.

Open /docs after clearing anon_id in browser DevTools. Loading /docs already
creates the cookie. Execute POST /api/v1/chats/ with {} and then GET:
the browser sends the same cookie automatically. Inspect Network request Cookie
and response Set-Cookie headers, and Application/Storage cookies.
Do not enter anon_id in Swagger or in JSON. HttpOnly prevents document.cookie access.

| Method | Path | Input | Success |
| --- | --- | --- | --- |
| POST | `/api/v1/chats/` | `{"title":"Договор"}` or `{}` | 201, ChatResponse |
| GET | `/api/v1/chats/` | `limit` (1–100, default 20), `offset` (>=0, default 0) | 200, ChatListResponse |
| GET | `/api/v1/chats/{chat_id}` | Integer chat id | 200, ChatResponse |
| PATCH | `/api/v1/chats/{chat_id}` | `{"title":"Новое название"}` | 200, ChatResponse |
| DELETE | `/api/v1/chats/{chat_id}` | Integer chat id | 204, empty body |

ChatResponse example (owner_id is never exposed):

```json
{"id":1,"title":"Договор","created_at":"2026-11-12T12:00:00","updated_at":"2026-11-12T12:30:00"}
```

ChatListResponse example:

```json
{"items":[],"total":0,"limit":20,"offset":0}
```

Titles are trimmed before enforcing 1–100 characters. Omitted or null creation
title becomes «Новый чат». PATCH requires a non-null title. Unknown input fields
and invalid pagination return FastAPI's JSON validation errors (422).
All reads, renames and deletes filter by cookie owner; foreign and missing chats
both return 404 with `{"detail":"Chat not found"}`.
Lists sort by updated_at descending, then id descending for deterministic ties.
Timestamps are UTC without a timezone suffix. Every rename refreshes updated_at.

Swagger is available at `/docs`, OpenAPI at `/openapi.json`.
`python -m pytest -q` uses a separate temporary SQLite database per integration
test and checks JSON contracts, Swagger, owner isolation and PostgreSQL DDL.
A live PostgreSQL integration run is not included.

## Messages API

`POST /api/v1/chats/{chat_id}/messages` accepts only `{"content":"Вопрос"}`.
Content is stripped and must contain 1–10,000 characters. The response is 201:
`{"user_message": MessageResponse, "assistant_message": MessageResponse}`.
Each message includes id, chat_id, role, content, status, sources, created_at,
and updated_at. Ownership is checked through Chat using the existing anon_id
dependency. Foreign and missing chats return the same 404.

The user message (completed) and an assistant placeholder (pending) are committed
before generation starts. The mock answer is then saved in a separate transaction.
Generation errors or invalid provider output produce an assistant message with
status failed, empty content and empty sources; POST still returns 201 because
the records were created. The original user message remains in history.
There is no retry endpoint, real LLM, RAG integration or background worker.
An interrupted process can leave a pending record for future recovery work.

`GET /api/v1/chats/{chat_id}/messages?limit=50&offset=0` returns
`{items, total, limit, offset}`. Limit is 1–100. History is sorted by created_at
ascending, then id ascending, and is never truncated in storage. Message dates
are returned as UTC with an explicit timezone; Chat retains its existing format.
Messages cannot be edited through the API.

The shared clock is `app/core/datetime.py::utc_now`; database columns in Chat
and Message use `app/db/types.py::UTCDateTime`. Values are stored as naive UTC
and restored as aware UTC on SQLite and PostgreSQL. Chat serialization retains
its existing timezone-less JSON format for API compatibility.

The first user message supplies the initial automatic title (whitespace collapsed,
first 100 characters), unless a title was explicitly set at creation or by rename.
The internal title_is_manual flag is not exposed in Chat responses. Adding user
or assistant messages refreshes Chat.updated_at. Deleting a chat cascades to all
messages, both through the ORM and through database foreign keys.

`app/services/ai_service.py` is the integration boundary:
`generate_reply({chat_id, message: {id, content}, history?: [{role, content}, ...]})`
returns `{content, sources}`. History can be supplied by internal callers; the API
does not fetch or select a last-N history window. Sources support document_id,
document_title, chunk_id, page, excerpt and url. Missing metadata is not invented
or returned as fabricated values. The mock returns an empty sources list.

For a new database, run `python -m scripts.init_db`. For an existing database,
run `python -m scripts.init_db --upgrade-messages` before starting the updated app.
This explicit, idempotent development upgrade adds title_is_manual and creates
messages. Historical titles are conservatively treated as manual since their
provenance is unknown. Back up a database before a schema upgrade. Production
schema changes still need versioned migrations; application startup never runs DDL.
The upgrade is tested on SQLite; PostgreSQL model DDL is compiled in tests.
ChatMemory remains a placeholder.
