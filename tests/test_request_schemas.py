"""Входные контракты и подключение пагинации через Query без внешних сервисов."""

from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.base import BaseRequest
from app.schemas.chat import ChatListQuery, ChatUpdate
from app.schemas.message import MessageCreate, MessageListQuery

TEXT_SCHEMAS = [(MessageCreate, "content", 10_000), (ChatUpdate, "title", 100)]
QUERY_SCHEMAS = [(ChatListQuery, 20), (MessageListQuery, 50)]
ALL_SCHEMAS = [MessageCreate, ChatUpdate, ChatListQuery, MessageListQuery]


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
@pytest.mark.parametrize("text", ["Вопрос юристу", "а"])
def test_valid_text(schema, field, maximum, text):
    assert getattr(schema(**{field: text}), field) == text


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
@pytest.mark.parametrize("value", ["", "   ", "\t\n\u00a0", None, 123, []])
def test_invalid_text(schema, field, maximum, value):
    with pytest.raises(ValidationError):
        schema(**{field: value})


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
def test_required_text(schema, field, maximum):
    with pytest.raises(ValidationError) as error:
        schema()
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
def test_strip_preserves_internal_formatting(schema, field, maximum):
    assert getattr(schema(**{field: " \tВопрос  юристу\nтекст\n "}), field) == "Вопрос  юристу\nтекст"


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
@pytest.mark.parametrize("padding", ["", " \t\n"])
def test_inclusive_maximum_after_strip(schema, field, maximum, padding):
    text = "я" * maximum
    assert getattr(schema(**{field: padding + text + padding}), field) == text


@pytest.mark.parametrize("schema,field,maximum", TEXT_SCHEMAS)
def test_over_maximum(schema, field, maximum):
    with pytest.raises(ValidationError) as error:
        schema(**{field: " " + "я" * (maximum + 1) + " "})
    assert error.value.errors()[0]["type"] == "string_too_long"


@pytest.mark.parametrize("schema", ALL_SCHEMAS)
def test_base_request_inheritance(schema):
    assert issubclass(schema, BaseRequest)
    assert schema.model_config["extra"] == "forbid"


@pytest.mark.parametrize("schema", ALL_SCHEMAS)
@pytest.mark.parametrize("field", ["role", "owner_id", "status", "sources", "id", "chat_id", "created_at", "updated_at", "unknown"])
def test_extra_fields_forbidden(schema, field):
    payload = {"content": "Вопрос"} if schema is MessageCreate else {"title": "Чат"} if schema is ChatUpdate else {}
    with pytest.raises(ValidationError) as error:
        schema(**payload, **{field: "assistant"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("schema,default_limit", QUERY_SCHEMAS)
def test_query_defaults(schema, default_limit):
    assert schema().model_dump() == {"limit": default_limit, "offset": 0}


@pytest.mark.parametrize("schema,default_limit", QUERY_SCHEMAS)
@pytest.mark.parametrize("limit", [1, 100])
@pytest.mark.parametrize("offset", [0, 15])
def test_query_boundaries(schema, default_limit, limit, offset):
    assert schema(limit=limit, offset=offset).model_dump() == {"limit": limit, "offset": offset}


@pytest.mark.parametrize("schema,default_limit", QUERY_SCHEMAS)
@pytest.mark.parametrize("payload", [{"limit": -1}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": 1.5}, {"offset": "invalid"}])
def test_invalid_query(schema, default_limit, payload):
    with pytest.raises(ValidationError):
        schema(**payload)


@pytest.fixture
def query_client():
    # Изолированные маршруты проверяют интеграцию схем, не реализуют API проекта.
    app = FastAPI()

    @app.get("/chats")
    def chats(query: Annotated[ChatListQuery, Query()]):
        return query.model_dump()

    @app.get("/chats/{chat_id}/messages")
    def messages(chat_id: str, query: Annotated[MessageListQuery, Query()]):
        return query.model_dump()

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path,default_limit", [("/chats", 20), ("/chats/test/messages", 50)])
def test_query_http_and_openapi(query_client, path, default_limit):
    response = query_client.get(path)
    assert response.status_code == 200
    assert response.json() == {"limit": default_limit, "offset": 0}
    response = query_client.get(path, params={"limit": "100", "offset": "15"})
    assert response.status_code == 200
    assert response.json() == {"limit": 100, "offset": 15}
    openapi_path = path.replace("test", "{chat_id}")
    operation = query_client.get("/openapi.json").json()["paths"][openapi_path]["get"]
    assert "requestBody" not in operation
    assert {p["name"] for p in operation["parameters"] if p["in"] == "query"} == {"limit", "offset"}


@pytest.mark.parametrize("path", ["/chats", "/chats/test/messages"])
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"owner_id": "forged"}])
def test_query_http_rejects_invalid_parameters(query_client, path, params):
    response = query_client.get(path, params=params)
    assert response.status_code == 422
    assert all(error["loc"][0] == "query" for error in response.json()["detail"])
