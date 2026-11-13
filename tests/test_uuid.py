"""UUID contracts on a fresh SQLite database and PostgreSQL DDL."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.api import dependencies
from app.db.models import Chat, Message
from test_chats_api import client, test_database
from test_messages_api import run_async


def test_uuid_generation_sqlite_roundtrip_and_foreign_key(client):
    async def check():
        async with dependencies.session_factory() as db, db.begin():
            chat = Chat(owner_id="alice", title="UUID")
            db.add(chat)
            await db.flush()
            message = Message(chat_id=chat.id, role="user", content="test")
            db.add(message)
            await db.flush()
            ids = chat.id, message.id
            assert all(isinstance(value, UUID) and value.version == 4 for value in ids)
            assert ids[0] != ids[1]
        async with dependencies.session_factory() as db, db.begin():
            assert (await db.get(Chat, ids[0])).id == ids[0]
            assert (await db.get(Message, ids[1])).chat_id == ids[0]
            await db.execute(delete(Chat).where(Chat.id == ids[0]))
        async with dependencies.session_factory() as db:
            assert await db.get(Message, ids[1]) is None
            db.add(Message(chat_id=uuid4(), role="user", content="orphan"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    run_async(check)


@pytest.mark.parametrize("method,suffix", [("get", ""), ("patch", ""), ("delete", ""),
                                          ("get", "/messages"), ("post", "/messages")])
@pytest.mark.parametrize("invalid", ["1", "-1", "not-a-uuid"])
def test_invalid_uuid(client, method, suffix, invalid):
    payload = {"json": {"title": "x"}} if method == "patch" else {"json": {"content": "x"}} if method == "post" else {}
    response = client.request(method, f"/api/v1/chats/{invalid}{suffix}", **payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "chat_id"]


def test_uuid_json_and_openapi(client):
    chat = client.post("/api/v1/chats/", json={}).json()
    assert UUID(chat["id"]).version == 4
    response = client.post(f"/api/v1/chats/{chat['id']}/messages", json={"content": "test"})
    assert response.status_code == 201
    for message in response.json().values():
        assert UUID(message["id"]).version == 4
        assert message["chat_id"] == chat["id"]
    document = client.get("/openapi.json").json()
    for path, operations in document["paths"].items():
        if "{chat_id}" in path:
            for operation in operations.values():
                parameter = next(p for p in operation["parameters"] if p["name"] == "chat_id")
                assert parameter["schema"]["format"] == "uuid"
    for schema, fields in [("ChatResponse", ["id"]), ("MessageResponse", ["id", "chat_id"])]:
        for field in fields:
            assert document["components"]["schemas"][schema]["properties"][field]["format"] == "uuid"


def test_uuid_postgresql_ddl():
    for model in (Chat, Message):
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "id UUID NOT NULL" in ddl and "SERIAL" not in ddl
        if model is Message:
            assert "chat_id UUID NOT NULL" in ddl
            assert "FOREIGN KEY(chat_id) REFERENCES chats (id) ON DELETE CASCADE" in ddl
