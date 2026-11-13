from collections.abc import Sequence
from datetime import datetime, timezone
from typing import get_type_hints
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.db.models import AnswerCitation, Message
from app.schemas.base import PaginatedResponse
from app.schemas.message import (
    MessageCreate, MessageExchangeResponse, MessageListResponse,
    MessageResponse, MessageSource,
)


@pytest.mark.parametrize('length', [1, 10_000])
def test_message_content_accepts_length_bounds_after_stripping(length):
    content = 'x' * length
    assert MessageCreate(content=f' \t{content}\n ').content == content


@pytest.mark.parametrize('content', ['', ' \t\n ', 'x' * 10_001, None, 123, [], {}])
def test_message_content_rejects_invalid_values(content):
    with pytest.raises(ValidationError):
        MessageCreate(content=content)


def test_message_content_is_required():
    with pytest.raises(ValidationError):
        MessageCreate()


@pytest.fixture
def message():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Message(
        id=uuid4(), chat_id=uuid4(), reply_to_message_id=None,
        role='user', content='  original content  ', status=None, error_code=None,
        created_at=now, updated_at=now,
    )


@pytest.mark.parametrize('container', [list, tuple])
def test_from_message_accepts_citation_sequences(message, container):
    citations = [AnswerCitation(
        chunk_id=uuid4(), document_id_snapshot=f'doc-{index}',
        document_title_snapshot=f'Document {index}', page_snapshot=index + 1,
        excerpt_snapshot='excerpt', url_snapshot='https://example.test',
        section_snapshot='section',
    ) for index in range(2)]
    response = MessageResponse.from_message(message, container(citations))
    assert get_type_hints(MessageResponse.from_message)['citations'] == Sequence[AnswerCitation]
    assert response.model_dump() == {
        'id': message.id, 'chat_id': message.chat_id, 'reply_to_message_id': None,
        'role': 'user', 'content': message.content, 'status': 'completed',
        'error_code': None, 'created_at': message.created_at, 'updated_at': message.updated_at,
        'sources': [{
            'document_id': citation.document_id_snapshot,
            'document_title': citation.document_title_snapshot,
            'chunk_id': citation.chunk_id, 'page': citation.page_snapshot,
            'excerpt': citation.excerpt_snapshot, 'url': citation.url_snapshot,
            'section': citation.section_snapshot,
        } for citation in citations],
    }
    assert message.status is None


@pytest.mark.parametrize('status', ['pending', 'completed', 'failed'])
def test_from_message_preserves_assistant_fields(message, status):
    message.role = 'assistant'
    message.status = status
    message.reply_to_message_id = uuid4()
    message.error_code = 'provider_error' if status == 'failed' else None
    response = MessageResponse.from_message(message)
    assert response.status == status
    assert response.role == 'assistant'
    assert response.reply_to_message_id == message.reply_to_message_id
    assert response.error_code == message.error_code
    assert response.sources == []


def test_message_source_allows_nullable_snapshot_fields():
    source = MessageSource.from_citation(AnswerCitation(document_title_snapshot='Document'))
    assert source.model_dump() == {
        'document_id': None, 'document_title': 'Document', 'chunk_id': None,
        'page': None, 'excerpt': None, 'url': None, 'section': None,
    }


@pytest.mark.parametrize('field', ['role', 'status'])
def test_message_response_rejects_unknown_literals(message, field):
    data = MessageResponse.from_message(message).model_dump()
    data[field] = 'invalid'
    with pytest.raises(ValidationError):
        MessageResponse(**data)


def test_message_list_and_exchange_serialization(message):
    response = MessageResponse.from_message(message)
    assert issubclass(MessageListResponse, PaginatedResponse)
    page = MessageListResponse(items=[response.model_dump()], total=1, limit=50, offset=0)
    assert isinstance(page.items[0], MessageResponse)
    assert page.model_dump() == {
        'items': [response.model_dump()], 'total': 1, 'limit': 50, 'offset': 0,
    }
    assert MessageListResponse.model_validate_json(page.model_dump_json()) == page
    exchange = MessageExchangeResponse(user_message=response, assistant_message=response)
    assert exchange.model_dump() == {
        'user_message': response.model_dump(), 'assistant_message': response.model_dump(),
    }
