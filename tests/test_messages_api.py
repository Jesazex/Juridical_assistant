"""Message API contracts, persistence, access control and generation failures."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import json

import pytest
from anyio.from_thread import start_blocking_portal
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from app.api import dependencies
from app.db.models.chat import Chat
from app.db.models.message import Message
from app.db.types import UTCDateTime
from app.core.datetime import utc_now
from app.services import ai_service
from app.services import message_service
from scripts.init_db import initialize
from test_chats_api import client, test_database  # shared isolated SQLite fixtures


def create_chat(client, payload=None):
    response = client.post("/api/v1/chats/", json=payload or {})
    assert response.status_code == 201
    return response.json()


def url(chat):
    return f"/api/v1/chats/{chat['id']}/messages"


def run_async(function):
    with start_blocking_portal() as portal:
        return portal.call(function)


def test_exchange_history_and_title(client):
    chat = create_chat(client)
    response = client.post(url(chat), json={"content": "  Первый\nвопрос  "})
    assert response.status_code == 201, response.text
    result = response.json()
    user, assistant = result["user_message"], result["assistant_message"]
    assert user["role"] == "user" and user["content"] == "Первый\nвопрос"
    assert assistant["role"] == "assistant" and assistant["content"] == "Тестовый ответ AI"
    for message in [user, assistant]:
        assert message["chat_id"] == chat["id"]
        assert message["status"] == "completed" and message["sources"] == []
        assert "owner_id" not in message
        assert datetime.fromisoformat(message["created_at"]).utcoffset().total_seconds() == 0
    assert user["id"] != assistant["id"]
    history = client.get(url(chat)).json()
    assert history == {"items": [user, assistant], "total": 2, "limit": 50, "offset": 0}
    updated = client.get(f"/api/v1/chats/{chat['id']}").json()
    assert updated["title"] == "Первый вопрос"
    assert updated["updated_at"] > chat["updated_at"]
    client.post(url(chat), json={"content": "Второй вопрос"})
    assert client.get(f"/api/v1/chats/{chat['id']}").json()["title"] == "Первый вопрос"
    assert client.get(url(chat)).json()["total"] == 4


@pytest.mark.parametrize("rename", [False, True])
def test_manual_title_preserved(client, rename):
    # Even a manually supplied default-looking title must be preserved.
    chat = create_chat(client, {} if rename else {"title": "Новый чат"})
    if rename:
        client.patch(f"/api/v1/chats/{chat['id']}", json={"title": "Новый чат"})
    client.post(url(chat), json={"content": "Question"})
    assert client.get(f"/api/v1/chats/{chat['id']}").json()["title"] == "Новый чат"


@pytest.mark.parametrize("payload", [
    {}, {"content": ""}, {"content": " \n\t"}, {"content": "a" * 10001},
    {"content": None}, {"content": 42}, {"content": []},
    *[{"content": "question", field: value} for field, value in [
        ("role", "assistant"), ("status", "completed"), ("chat_id", 1),
        ("owner_id", "bob"), ("sources", []), ("id", 1),
    ]],
])
def test_validation(client, payload):
    chat = create_chat(client)
    assert client.post(url(chat), json=payload).status_code == 422
    assert client.get(url(chat)).json()["total"] == 0


def test_max_length_and_title_truncation(client):
    chat = create_chat(client)
    assert client.post(url(chat), json={"content": " " + "я" * 10000 + " "}).status_code == 201
    assert client.get(f"/api/v1/chats/{chat['id']}").json()["title"] == "я" * 100


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                      {"limit": "x"}, {"role": "assistant"}])
def test_invalid_pagination(client, params):
    chat = create_chat(client)
    assert client.get(url(chat), params=params).status_code == 422


def test_pagination_and_tied_timestamps_without_history_cap(client):
    chat = create_chat(client)

    async def seed():
        async with dependencies.session_factory() as db, db.begin():
            db.add_all([Message(chat_id=UUID(chat["id"]), role="user", content=str(i),
                                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
                        for i in range(125)])
    run_async(seed)
    first = client.get(url(chat)).json()
    assert first["total"] == 125 and len(first["items"]) == 50
    all_items = client.get(url(chat), params={"limit": 100}).json()["items"]
    all_items += client.get(url(chat), params={"limit": 100, "offset": 100}).json()["items"]
    assert {item["content"] for item in all_items} == {str(i) for i in range(125)}
    assert [item["id"] for item in all_items] == sorted(item["id"] for item in all_items)
    assert client.get(url(chat), params={"offset": 125}).json()["items"] == []


@pytest.mark.parametrize("method", ["get", "post"])
def test_owner_isolation_and_missing_chat(client, method):
    chat = create_chat(client)
    client.post(url(chat), json={"content": "private"})
    client.cookies.set("anon_id", "bob")
    for path in [url(chat), f"/api/v1/chats/{uuid4()}/messages"]:
        response = client.request(method, path, **({"json": {"content": "x"}} if method == "post" else {}))
        assert response.status_code == 404 and response.json() == {"detail": "Chat not found"}
    other = create_chat(client)
    assert client.get(url(other)).json()["total"] == 0


def test_sources_and_committed_pending_state(client, monkeypatch):
    chat = create_chat(client)
    sources = [{"document_id": "law", "document_title": "Закон", "chunk_id": 7,
                "page": 3, "excerpt": "Фрагмент", "url": "https://example.org/law"},
               {"document_id": 2}]

    async def generate(payload):
        assert json.loads(json.dumps(payload)) == payload
        assert payload["chat_id"] == chat["id"] and payload["message"]["content"] == "question"
        assert "history" not in payload
        # A separate connection must see both records before generation begins.
        async with dependencies.session_factory() as db:
            items = list(await db.scalars(select(Message).order_by(Message.created_at, Message.id)))
            assert [(item.role, item.status) for item in items] == [
                ("user", "completed"), ("assistant", "pending")]
        return {"content": "answer", "sources": sources}

    monkeypatch.setattr(ai_service, "generate_reply", generate)
    response = client.post(url(chat), json={"content": "question"})
    assert response.status_code == 201
    assert response.json()["assistant_message"]["sources"] == sources
    assert client.get(url(chat)).json()["items"][1]["sources"] == sources


@pytest.mark.parametrize("result", [None, {}, {"content": " "},
    {"content": "x", "sources": [{"page": "unknown"}]},
    {"content": "x", "sources": [{"made_up": 1}]}])
def test_generation_failure_preserves_input(client, monkeypatch, result):
    chat = create_chat(client)

    async def generate(payload):
        if result is None:
            raise RuntimeError("sensitive provider error")
        return result

    monkeypatch.setattr(ai_service, "generate_reply", generate)
    response = client.post(url(chat), json={"content": "keep me"})
    assert response.status_code == 201
    assert "sensitive" not in response.text
    items = client.get(url(chat)).json()["items"]
    assert len(items) == 2 and items[0]["content"] == "keep me"
    assert items[1]["status"] == "failed" and items[1]["content"] == ""
    assert items[1]["sources"] == []


def test_cascade_and_no_edit_routes(client):
    chat = create_chat(client)
    client.post(url(chat), json={"content": "question"})
    assert client.patch(url(chat), json={"content": "edit"}).status_code == 405
    assert client.patch(url(chat) + "/1", json={"content": "edit"}).status_code == 404
    assert client.delete(f"/api/v1/chats/{chat['id']}").status_code == 204

    async def remaining():
        async with dependencies.session_factory() as db:
            return await db.scalar(select(func.count()).select_from(Message))
    assert run_async(remaining) == 0
    assert client.get(url(chat)).status_code == 404


def test_database_cascade_and_utc_roundtrip(client):
    chat = create_chat(client)
    client.post(url(chat), json={"content": "x"})

    async def check():
        async with dependencies.session_factory() as db, db.begin():
            message = await db.scalar(select(Message))
            assert message.created_at.utcoffset().total_seconds() == 0
            await db.execute(delete(Chat).where(Chat.id == UUID(chat["id"])))
            assert await db.scalar(select(func.count()).select_from(Message)) == 0
    run_async(check)


def test_models_postgresql_ddl():
    ddl = str(CreateTable(Message.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE CASCADE" in ddl and "JSON" in ddl
    assert "owner_id" not in Message.__table__.columns
    assert "message_role" in ddl and "message_status" in ddl


def test_utc_type_on_sqlite_and_postgresql(client):
    from sqlalchemy.dialects import sqlite

    offset_time = datetime(2026, 11, 12, 15, 0, tzinfo=timezone(timedelta(hours=3)))
    expected = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    column_type = UTCDateTime()
    for dialect in [sqlite.dialect(), postgresql.dialect()]:
        stored = column_type.bind_processor(dialect)(offset_time)
        loaded = column_type.result_processor(dialect, None)(stored)
        assert loaded == expected and loaded.tzinfo is timezone.utc
        assert column_type.process_result_value(offset_time, dialect) == expected
        assert column_type.process_bind_param(None, dialect) is None
        assert column_type.process_result_value(None, dialect) is None
    assert utc_now().tzinfo is timezone.utc

    chat = create_chat(client)

    async def check():
        async with dependencies.session_factory() as db, db.begin():
            stored_chat = await db.get(Chat, UUID(chat["id"]))
            stored_chat.updated_at = offset_time
            db.add(Message(chat_id=UUID(chat["id"]), role="user", content="UTC", created_at=offset_time))
        async with dependencies.session_factory() as db:
            loaded_chat = await db.get(Chat, UUID(chat["id"]))
            message = await db.scalar(select(Message))
            assert loaded_chat.updated_at == expected
            assert message.created_at == expected
    run_async(check)
    # Chat keeps its existing JSON format; Message keeps its explicit UTC offset.
    assert client.get(f"/api/v1/chats/{chat['id']}").json()["updated_at"] == "2026-11-12T12:00:00"
    assert datetime.fromisoformat(client.get(url(chat)).json()["items"][0]["created_at"]) == expected


def test_optional_history_is_forwarded_without_selection(client, monkeypatch):
    chat = create_chat(client)
    history = [{"role": "user", "content": str(i)} for i in range(25)]
    captured = []

    async def generate(payload):
        captured.append(payload)
        return {"content": "answer", "sources": []}

    monkeypatch.setattr(ai_service, "generate_reply", generate)

    async def send():
        async with dependencies.session_factory() as db:
            return await message_service.create_message(db, "alice", UUID(chat["id"]), "new", history)
    assert run_async(send).assistant_message.status == "completed"
    assert captured[0]["history"] == history
    assert client.get(url(chat)).json()["total"] == 2


def test_message_histories_are_scoped_to_chat(client):
    first, second = create_chat(client), create_chat(client)
    client.post(url(first), json={"content": "first only"})
    assert client.get(url(second)).json()["total"] == 0


def test_chat_deleted_during_generation_is_not_resurrected(client, monkeypatch):
    chat = create_chat(client)

    async def generate(payload):
        async with dependencies.session_factory() as db, db.begin():
            await db.execute(delete(Chat).where(Chat.id == UUID(chat["id"])))
        return {"content": "too late", "sources": []}

    monkeypatch.setattr(ai_service, "generate_reply", generate)
    assert client.post(url(chat), json={"content": "question"}).status_code == 404

    async def count():
        async with dependencies.session_factory() as db:
            return await db.scalar(select(func.count()).select_from(Message))
    assert run_async(count) == 0


def test_messages_openapi(client):
    document = client.get("/openapi.json").json()
    operations = document["paths"]["/api/v1/chats/{chat_id}/messages"]
    assert set(operations) == {"post", "get"}
    assert "requestBody" not in operations["get"]
    assert "201" in operations["post"]["responses"]
    create_schema = document["components"]["schemas"]["MessageCreate"]
    assert set(create_schema["properties"]) == {"content"}
    assert create_schema["additionalProperties"] is False


def test_existing_database_upgrade(tmp_path):
    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE TABLE chats (id INTEGER PRIMARY KEY, title VARCHAR(100))"))
                await connection.execute(text("INSERT INTO chats (title) VALUES ('Old title')"))
                with pytest.raises(RuntimeError, match="upgrade-messages"):
                    await connection.run_sync(initialize)
                await connection.run_sync(initialize, True)
                await connection.run_sync(initialize, True)
                assert (await connection.execute(text("SELECT title_is_manual FROM chats"))).scalar() == 1
                assert (await connection.execute(text("SELECT count(*) FROM messages"))).scalar() == 0
        finally:
            await engine.dispose()
    run_async(check)
