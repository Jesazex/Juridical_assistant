from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.db.models import Chat
from app.schemas.base import PaginatedResponse
from app.schemas.chat import ChatCreate, ChatListResponse, ChatResponse, ChatUpdate


@pytest.mark.parametrize('model', [ChatCreate, ChatUpdate])
@pytest.mark.parametrize('length', [1, 100])
def test_chat_title_accepts_length_bounds_after_stripping(model, length):
    title = 'x' * length
    assert model(title=f' \t{title}\n ').title == title


@pytest.mark.parametrize('model', [ChatCreate, ChatUpdate])
@pytest.mark.parametrize('title', ['', ' \t\n ', 'x' * 101, 123, [], {}])
def test_chat_title_rejects_invalid_values(model, title):
    with pytest.raises(ValidationError):
        model(title=title)


def test_chat_create_allows_missing_or_null_title():
    assert ChatCreate().title is None
    assert ChatCreate(title=None).title is None
    assert ChatCreate().model_dump(exclude_unset=True) == {}
    assert ChatCreate(title=None).model_dump(exclude_unset=True) == {'title': None}


@pytest.mark.parametrize('data', [{}, {'title': None}])
def test_chat_update_requires_non_null_title(data):
    with pytest.raises(ValidationError):
        ChatUpdate(**data)


def test_chat_response_reads_orm_attributes_and_serializes_page():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chat = Chat(id=uuid4(), title='  Original title  ', created_at=now, updated_at=now)
    response = ChatResponse.model_validate(chat)
    assert response.model_dump() == {
        'id': chat.id, 'title': chat.title, 'created_at': now, 'updated_at': now,
    }
    assert issubclass(ChatListResponse, PaginatedResponse)
    page = ChatListResponse(items=[response.model_dump()], total=1, limit=20, offset=0)
    assert isinstance(page.items[0], ChatResponse)
    assert page.model_dump() == {
        'items': [response.model_dump()], 'total': 1, 'limit': 20, 'offset': 0,
    }
    assert ChatListResponse.model_validate_json(page.model_dump_json()) == page
