"""HTTP integration tests against a fresh, separate SQLite database per test."""
from datetime import datetime
from uuid import UUID

import pytest
from anyio.from_thread import start_blocking_portal
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy.pool import NullPool

from app.api import dependencies
from app.db.database import Base
from app.db.models.chat import Chat
from app.main import app

URL = "/api/v1/chats/"


@pytest.fixture(scope="function")
def test_database(tmp_path, monkeypatch):
    # Setup and HTTP requests run in different portals; do not share pooled connections.
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        poolclass=NullPool,
    )
    monkeypatch.setattr(
        dependencies, "session_factory", async_sessionmaker(engine, expire_on_commit=False)
    )

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    with start_blocking_portal() as portal:
        try:
            portal.call(setup)
            yield
        finally:
            portal.call(engine.dispose)


@pytest.fixture(scope="function")
def client(test_database):
    with TestClient(app) as http:
        http.cookies.set("anon_id", "alice")
        yield http


def assert_chat(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert set(data) == {"id", "title", "created_at", "updated_at"}
    assert isinstance(data["id"], int)
    datetime.fromisoformat(data["created_at"])
    datetime.fromisoformat(data["updated_at"])
    return data


@pytest.mark.parametrize("payload,title", [
    ({}, "Новый чат"), ({"title": None}, "Новый чат"),
    ({"title": " \tВопрос по договору\n "}, "Вопрос по договору"),
    ({"title": " " + "я" * 100 + " "}, "я" * 100),
])
def test_create_and_get(client, payload, title):
    data = assert_chat(client.post(URL, json=payload), 201)
    assert data["title"] == title
    assert assert_chat(client.get(URL + str(data["id"]))) == data


@pytest.mark.parametrize("payload", [
    {"title": ""}, {"title": "\t\n\u00a0"}, {"title": "я" * 101},
    {"title": 123}, {"title": []}, {"owner_id": "bob"}, {"id": 1},
    {"created_at": "2026-01-01"},
])
def test_create_validation(client, payload):
    response = client.post(URL, json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get(URL).json()["total"] == 0


@pytest.mark.parametrize("method,path,payload", [
    ("post", "", {}), ("get", "", None), ("get", "1", None),
    ("patch", "1", {"title": "Новое"}), ("delete", "1", None),
])
@pytest.mark.parametrize("cookie", [None, "", "   "])
def test_missing_identity(client, method, path, payload, cookie):
    client.cookies.clear()
    if cookie is not None:
        client.cookies.set("anon_id", cookie)
    response = client.request(method, URL + path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == (201 if method == "post" else 200 if path == "" else 404)
    generated = response.cookies["anon_id"]
    assert UUID(generated).version == 4
    for attribute in ["HttpOnly", "SameSite=lax", "Path=/", "Max-Age=2592000"]:
        assert attribute in response.headers["set-cookie"]
    client.cookies.clear()
    client.cookies.set("anon_id", generated)
    repeated = client.get(URL)
    assert "set-cookie" not in repeated.headers
    assert repeated.json()["total"] == (1 if method == "post" else 0)


def test_pagination_sorting_and_isolation(client):
    first = client.post(URL, json={"title": "Первый"}).json()
    second = client.post(URL, json={"title": "Второй"}).json()
    client.cookies.set("anon_id", "bob")
    assert client.get(URL).json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    client.post(URL, json={"title": "Чужой"})
    client.cookies.set("anon_id", "alice")
    response = client.get(URL)
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"items": [second, first], "total": 2, "limit": 20, "offset": 0}
    assert client.get(URL, params={"limit": 1, "offset": 1}).json() == {
        "items": [first], "total": 2, "limit": 1, "offset": 1,
    }
    assert client.get(URL, params={"offset": 100}).json()["items"] == []
    changed = assert_chat(client.patch(URL + str(first["id"]), json={"title": "  Новое  "}))
    assert changed["title"] == "Новое"
    assert changed["created_at"] == first["created_at"]
    assert changed["updated_at"] > first["updated_at"]
    assert client.get(URL).json()["items"] == [changed, second]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                       {"limit": "x"}, {"owner_id": "bob"}])
def test_invalid_pagination(client, params):
    assert client.get(URL, params=params).status_code == 422


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_foreign_and_missing_chat(client, method):
    own = client.post(URL, json={"title": "Личный"}).json()
    client.cookies.set("anon_id", "bob")
    kwargs = {"json": {"title": "Взлом"}} if method == "patch" else {}
    for chat_id in [own["id"], 999999]:
        response = client.request(method, URL + str(chat_id), **kwargs)
        assert response.status_code == 404
        assert response.json() == {"detail": "Chat not found"}
    client.cookies.set("anon_id", "alice")
    assert assert_chat(client.get(URL + str(own["id"]))) == own


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"title": " "},
                                      {"title": "я" * 101}, {"title": "Да", "owner_id": "bob"}])
def test_update_validation(client, payload):
    own = client.post(URL, json={}).json()
    assert client.patch(URL + str(own["id"]), json=payload).status_code == 422
    assert client.get(URL + str(own["id"])).json() == own


def test_delete(client):
    own = client.post(URL, json={}).json()
    response = client.delete(URL + str(own["id"]))
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(URL + str(own["id"])).status_code == 404
    assert client.delete(URL + str(own["id"])).status_code == 404
    assert client.get(URL).json()["total"] == 0


def test_swagger_openapi_and_existing_health(client):
    assert client.get("/docs").status_code == 200
    document = client.get("/openapi.json").json()
    for path, methods in [(URL, {"post": "201", "get": "200"}),
                          (URL + "{chat_id}", {"get": "200", "patch": "200", "delete": "204"})]:
        for method, code in methods.items():
            operation = document["paths"][path][method]
            response = operation["responses"][code]
            if code == "204":
                assert "content" not in response
            else:
                assert "$ref" in response["content"]["application/json"]["schema"]
            assert not any(p["in"] == "cookie" for p in operation.get("parameters", []))
    assert "requestBody" not in document["paths"][URL]["get"]
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_postgresql_ddl_and_owner_index():
    ddl = str(CreateTable(Chat.__table__).compile(dialect=postgresql.dialect()))
    assert "SERIAL" in ddl
    assert "VARCHAR(100)" in ddl
    assert any([column.name for column in index.columns] == ["owner_id"] for index in Chat.__table__.indexes)
    assert not inspect(Chat).relationships  # Message and ChatMemory are still empty placeholders.


def test_update_same_title_refreshes_timestamp(client):
    original = assert_chat(client.post(URL, json={"title": "Договор"}), 201)
    updated = assert_chat(client.patch(URL + str(original["id"]), json={"title": "Договор"}))
    assert updated["title"] == original["title"]
    assert updated["created_at"] == original["created_at"]
    assert updated["updated_at"] > original["updated_at"]




@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/api/v1/health", "/missing"])
def test_cookie_on_every_route(client, path):
    client.cookies.clear()
    response = client.get(path)
    assert UUID(response.cookies["anon_id"]).version == 4
    assert "set-cookie" not in client.get(path).headers


def test_secure_cookie(client, monkeypatch):
    from app.main import settings
    monkeypatch.setattr(settings, "anon_cookie_secure", True)
    client.cookies.clear()
    assert "Secure" in client.get("/docs").headers["set-cookie"]


def test_cors_configuration():
    from fastapi import FastAPI
    from pydantic import ValidationError
    from starlette.middleware.cors import CORSMiddleware
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(cors_origins=["*"], _env_file=None)
    config = Settings(cors_origins=["http://localhost:5173"], _env_file=None)
    api = FastAPI()
    api.add_middleware(CORSMiddleware, allow_origins=config.cors_origins,
                       allow_credentials=True, allow_methods=["POST"],
                       allow_headers=["Content-Type"])
    with TestClient(api) as http:
        headers = {"Origin": config.cors_origins[0],
                   "Access-Control-Request-Method": "POST"}
        response = http.options("/", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == config.cors_origins[0]
        assert response.headers["access-control-allow-credentials"] == "true"
        headers["Origin"] = "https://untrusted.example"
        assert http.options("/", headers=headers).status_code == 400