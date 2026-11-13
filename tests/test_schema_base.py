import pytest
from pydantic import ValidationError

from app.schemas.base import BaseRequest, PaginatedResponse, PaginationQuery, validate_text
from app.schemas.chat import ChatCreate, ChatListQuery, ChatUpdate
from app.schemas.message import MessageCreate, MessageListQuery


@pytest.mark.parametrize(
    ('value', 'expected'),
    [('  text  ', 'text'), ('\t\ntext\r\n', 'text'),
     (' one  two ', 'one  two'), ('', ''), (' \t\n', '')],
)
def test_validate_text_strips_only_outer_whitespace(value, expected):
    assert validate_text(value) == expected


@pytest.mark.parametrize('value', [None, 123, 1.5, True, b' text ', [], {}, object()])
def test_validate_text_preserves_non_strings(value):
    assert validate_text(value) is value


@pytest.mark.parametrize(
    ('model', 'data'),
    [(BaseRequest, {}), (PaginationQuery, {}), (ChatCreate, {}),
     (ChatUpdate, {'title': 'title'}), (MessageCreate, {'content': 'text'}),
     (ChatListQuery, {}), (MessageListQuery, {})],
)
def test_requests_forbid_extra_fields(model, data):
    assert issubclass(model, BaseRequest)
    with pytest.raises(ValidationError) as exc:
        model(**data, unexpected=True)
    assert [(error['loc'], error['type']) for error in exc.value.errors()] == [
        (('unexpected',), 'extra_forbidden')
    ]


@pytest.mark.parametrize(
    ('model', 'default_limit'),
    [(PaginationQuery, 20), (ChatListQuery, 20), (MessageListQuery, 50)],
)
def test_pagination_defaults_and_inheritance(model, default_limit):
    assert issubclass(model, PaginationQuery)
    assert model().model_dump() == {'limit': default_limit, 'offset': 0}


@pytest.mark.parametrize('model', [PaginationQuery, ChatListQuery, MessageListQuery])
@pytest.mark.parametrize('limit', [1, 100])
def test_pagination_accepts_bounds(model, limit):
    assert model(limit=limit, offset=0).model_dump() == {'limit': limit, 'offset': 0}
    assert model(limit=str(limit), offset='123').offset == 123


@pytest.mark.parametrize('model', [PaginationQuery, ChatListQuery, MessageListQuery])
@pytest.mark.parametrize(
    ('data', 'field', 'error_type'),
    [({'limit': 0}, 'limit', 'greater_than_equal'),
     ({'limit': 101}, 'limit', 'less_than_equal'),
     ({'offset': -1}, 'offset', 'greater_than_equal')],
)
def test_pagination_rejects_out_of_bounds(model, data, field, error_type):
    with pytest.raises(ValidationError) as exc:
        model(**data)
    assert exc.value.errors()[0]['loc'] == (field,)
    assert exc.value.errors()[0]['type'] == error_type


def test_paginated_response_validates_item_type():
    page = PaginatedResponse[int](items=['1', 2], total=2, limit=20, offset=0)
    assert page.model_dump() == {'items': [1, 2], 'total': 2, 'limit': 20, 'offset': 0}
    with pytest.raises(ValidationError):
        PaginatedResponse[int](items=['invalid'], total=1, limit=20, offset=0)
