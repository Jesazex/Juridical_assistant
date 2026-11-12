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

Every request must include a nonempty `anon_id` cookie, for example
`Cookie: anon_id=alice`. Missing/blank identity returns 401 with
`{"detail":"anon_id cookie is required"}`. The API does not issue cookies or
register users. A caller must retain its anonymous identifier between requests.

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

Message and ChatMemory models are currently empty. When implementing them, add
foreign keys and deletion cascades together with tests for chat deletion.
