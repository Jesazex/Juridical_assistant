import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import ANONYMOUS_COOKIE, token_hash
from app.db.base import Base
from app.db.models import (
    AnonymousUser, AnswerCitation, Chat, ChatMemory, Document, DocumentChunk,
    DocumentVersion, Message,
)
from app.db.session import create_database_engine, get_database_url
from app.main import app
from app.schemas.base import PaginatedResponse
from app.schemas.chat import ChatCreate, ChatListResponse, ChatResponse, ChatUpdate
from app.services import chat_service


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


def validate_test_database_url(value, production=None):
    """Validate the target before any connection or test DDL is attempted."""
    url = make_url(value)
    if url.drivername != 'postgresql+asyncpg' or not (url.database or '').endswith('_test'):
        raise ValueError('TEST_DATABASE_URL must use postgresql+asyncpg and a database ending in _test')
    if production is not None and url.database == production.database:
        raise ValueError('The test database must differ from the application database')
    return url


@pytest.fixture(scope='module')
def chat_database_url():
    """Use the existing Compose PostgreSQL server and a separate test database."""
    settings = dotenv_values(Path(__file__).resolve().parents[1] / '.env', interpolate=False)
    value = os.environ.get('TEST_DATABASE_URL', settings.get('TEST_DATABASE_URL'))
    if not value:
        pytest.skip('TEST_DATABASE_URL is not set: start Compose knowledge-db and create psb_knowledge_test')
    try:
        production = get_database_url()
    except RuntimeError:
        production = None
    url = validate_test_database_url(value, production)

    async def prepare():
        engine = create_database_engine(url)
        try:
            async with engine.begin() as connection:
                actual_database = await connection.scalar(text('SELECT current_database()'))
                if actual_database != url.database:
                    raise ValueError('Connected database does not match TEST_DATABASE_URL')
                await connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public'))
                await connection.execute(text('CREATE SCHEMA IF NOT EXISTS knowledge'))
                await connection.execute(text('CREATE SCHEMA IF NOT EXISTS chat'))
                # Reuse all production models, including pgvector and cross-schema FKs.
                # Existing tables are neither dropped nor truncated. This tests model DDL,
                # not Alembic history (whose baseline requires the production DB name).
                await connection.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(prepare())
    return url


@pytest.fixture
def chat_api(chat_database_url, monkeypatch):
    """Run each scenario on PostgreSQL savepoints, then roll back its outer transaction."""
    def run(scenario):
        async def execute():
            engine = create_database_engine(chat_database_url)
            try:
                async with engine.connect() as connection:
                    transaction = await connection.begin()
                    factory = async_sessionmaker(
                        connection, expire_on_commit=False, join_transaction_mode='create_savepoint',
                    )
                    monkeypatch.setattr(app.state, 'session_factory', factory, raising=False)
                    monkeypatch.setattr(app.state, 'cookie_secure', False)
                    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                    try:
                        async with (
                            httpx.AsyncClient(transport=transport, base_url='http://test') as client,
                            httpx.AsyncClient(transport=transport, base_url='http://test') as other,
                        ):
                            await scenario(client, other, factory)
                    finally:
                        await transaction.rollback()
            finally:
                await engine.dispose()
        asyncio.run(execute())
    return run


async def create_api_chat(client, body=None):
    response = await client.post('/api/v1/chats/', json={} if body is None else body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize('body', [{}, {'title': None}, {'title': '  My title  '}])
def test_api_create_chat_and_cookie(chat_api, body):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client, body)
        assert set(chat) == {'id', 'title', 'created_at', 'updated_at'}
        assert UUID(chat['id']).version == 4
        assert datetime.fromisoformat(chat['created_at']).tzinfo is not None
        assert chat['created_at'] == chat['updated_at']
        custom = body.get('title') is not None
        assert chat['title'] == ('My title' if custom else 'Новый чат')
        cookie = client.cookies[ANONYMOUS_COOKIE]
        assert len(cookie) == 43
        async with factory() as session:
            stored = await session.get(Chat, UUID(chat['id']))
            owner = await session.scalar(select(AnonymousUser).where(
                AnonymousUser.token_hash == token_hash(cookie),
            ))
            assert stored.owner_id == owner.id
            assert stored.is_title_custom is custom
        fetched = await client.get(f"/api/v1/chats/{chat['id']}")
        assert fetched.status_code == 200
        assert fetched.json() == chat
        assert 'set-cookie' not in fetched.headers
        assert fetched.headers['cache-control'] == 'no-store'
    chat_api(scenario)


def test_api_cookie_attributes_and_invalid_cookie_replacement(chat_api):
    async def scenario(client, other, factory):
        client.cookies.set(ANONYMOUS_COOKIE, 'invalid')
        response = await client.get('/api/v1/chats/')
        assert response.status_code == 200
        cookie = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie
        assert 'path=/' in cookie and 'max-age=2592000' in cookie
        assert len(response.cookies[ANONYMOUS_COOKIE]) == 43
    chat_api(scenario)


@pytest.mark.parametrize('method', ['GET', 'PATCH', 'DELETE'])
def test_api_foreign_and_missing_chats_have_identical_404(chat_api, method):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        options = {'json': {'title': 'stolen'}} if method == 'PATCH' else {}
        foreign = await other.request(method, f"/api/v1/chats/{chat['id']}", **options)
        missing = await other.request(method, f'/api/v1/chats/{uuid4()}', **options)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() == {'detail': 'Chat not found'}
        assert (await client.get(f"/api/v1/chats/{chat['id']}")).json() == chat
    chat_api(scenario)


def test_api_owner_isolation_pagination_and_stable_order(chat_api):
    async def scenario(client, other, factory):
        chats = [await create_api_chat(client, {'title': str(index)}) for index in range(4)]
        foreign = await create_api_chat(other)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        async with factory.begin() as session:
            for index, chat in enumerate(chats):
                await session.execute(update(Chat).where(Chat.id == UUID(chat['id'])).values(
                    updated_at=now + timedelta(days=1 if index == 0 else 0),
                ))
        expected = [chats[0]['id']] + sorted([chat['id'] for chat in chats[1:]], reverse=True)
        response = (await client.get('/api/v1/chats/')).json()
        assert (response['limit'], response['offset'], response['total']) == (20, 0, 4)
        assert [chat['id'] for chat in response['items']] == expected
        page = (await client.get('/api/v1/chats/', params={'limit': 2, 'offset': 1})).json()
        assert (page['limit'], page['offset'], page['total']) == (2, 1, 4)
        assert [chat['id'] for chat in page['items']] == expected[1:3]
        maximum = await client.get('/api/v1/chats/', params={'limit': 100})
        assert maximum.status_code == 200 and maximum.json()['limit'] == 100
        minimum = await client.get('/api/v1/chats/', params={'limit': 1})
        assert minimum.status_code == 200 and len(minimum.json()['items']) == 1
        empty = (await client.get('/api/v1/chats/', params={'offset': 99})).json()
        assert empty['items'] == [] and empty['total'] == 4
        isolated = (await other.get('/api/v1/chats/')).json()
        assert isolated['total'] == 1 and isolated['items'] == [foreign]
    chat_api(scenario)


@pytest.mark.parametrize('params', [
    {'limit': 0}, {'limit': 101}, {'offset': -1}, {'limit': 'bad'}, {'owner_id': str(uuid4())},
])
def test_api_rejects_invalid_pagination(chat_api, params):
    async def scenario(client, other, factory):
        assert (await client.get('/api/v1/chats/', params=params)).status_code == 422
    chat_api(scenario)


def test_api_rename_updates_custom_flag_and_activity(chat_api):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        response = await client.patch(f"/api/v1/chats/{chat['id']}", json={'title': '  Renamed  '})
        assert response.status_code == 200
        renamed = response.json()
        assert renamed['title'] == 'Renamed'
        assert renamed['created_at'] == chat['created_at']
        assert datetime.fromisoformat(renamed['updated_at']) > datetime.fromisoformat(chat['updated_at'])
        async with factory() as session:
            stored = await session.get(Chat, UUID(chat['id']))
            assert stored.is_title_custom is True
        assert (await client.get(f"/api/v1/chats/{chat['id']}")).json() == renamed
    chat_api(scenario)


@pytest.mark.parametrize('method', ['POST', 'PATCH'])
@pytest.mark.parametrize('body', [
    {'title': ''}, {'title': ' \t\n '}, {'title': 'x' * 101},
    {'owner_id': str(uuid4()), 'title': 'title'},
])
def test_api_rejects_invalid_titles_and_owner_body(chat_api, method, body):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        path = '/api/v1/chats/' if method == 'POST' else f"/api/v1/chats/{chat['id']}"
        assert (await client.request(method, path, json=body)).status_code == 422
        assert (await client.get(f"/api/v1/chats/{chat['id']}")).json() == chat
        assert (await client.get('/api/v1/chats/')).json()['total'] == 1
    chat_api(scenario)


@pytest.mark.parametrize('method', ['GET', 'PATCH', 'DELETE'])
def test_api_rejects_invalid_path_uuid(chat_api, method):
    async def scenario(client, other, factory):
        options = {'json': {'title': 'title'}} if method == 'PATCH' else {}
        assert (await client.request(method, '/api/v1/chats/not-a-uuid', **options)).status_code == 422
    chat_api(scenario)


def test_api_delete_is_persistent(chat_api):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        path = f"/api/v1/chats/{chat['id']}"
        response = await client.delete(path)
        assert response.status_code == 204 and response.content == b''
        assert (await client.get(path)).status_code == 404
        assert (await client.delete(path)).status_code == 404
        assert (await client.get('/api/v1/chats/')).json()['total'] == 0
    chat_api(scenario)


@pytest.mark.parametrize('error, expected_status', [(chat_service.ChatNotFound, 404), (RuntimeError, 500)])
def test_api_transaction_rolls_back_partial_write(chat_api, monkeypatch, error, expected_status):
    original = chat_service.create_chat

    async def fail_after_write(session, owner_id, title):
        await original(session, owner_id, title)
        raise error('test rollback')

    async def scenario(client, other, factory):
        assert (await client.get('/api/v1/chats/')).status_code == 200
        monkeypatch.setattr(chat_service, 'create_chat', fail_after_write)
        response = await client.post('/api/v1/chats/', json={})
        assert response.status_code == expected_status
        assert (await client.get('/api/v1/chats/')).json()['total'] == 0
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(AnonymousUser).where(
                AnonymousUser.token_hash == token_hash(client.cookies[ANONYMOUS_COOKIE]),
            )) == 1
    chat_api(scenario)


def test_chat_routes_registered_in_application():
    paths = app.openapi()['paths']
    assert set(paths['/api/v1/chats/']) == {'get', 'post'}
    assert set(paths['/api/v1/chats/{chat_id}']) == {'get', 'patch', 'delete'}
    assert paths['/api/v1/chats/']['post']['responses'].get('201')
    assert paths['/api/v1/chats/{chat_id}']['delete']['responses'].get('204')
    assert not any('messages' in path or 'documents' in path for path in paths)


@pytest.mark.parametrize('value', [
    'sqlite+aiosqlite:///test.db',
    'postgresql://localhost/psb_knowledge_test',
    'postgresql+asyncpg://localhost/psb_knowledge',
    'postgresql+asyncpg://localhost/postgres',
    'postgresql+asyncpg://localhost/',
])
def test_database_guard_rejects_unsafe_targets(value):
    with pytest.raises(ValueError):
        validate_test_database_url(value)


def test_database_guard_rejects_application_database_even_with_test_suffix():
    url = 'postgresql+asyncpg://localhost/custom_test'
    with pytest.raises(ValueError, match='must differ'):
        validate_test_database_url(url, make_url(url))


def test_database_guard_accepts_separate_compose_database():
    url = validate_test_database_url(
        'postgresql+asyncpg://localhost:5433/psb_knowledge_test',
        make_url('postgresql+asyncpg://localhost:5433/psb_knowledge'),
    )
    assert url.database == 'psb_knowledge_test'


@pytest.mark.parametrize('operation', ['get_chat', 'rename_chat', 'delete_chat'])
def test_service_forwards_owner_and_raises_for_missing_chat(monkeypatch, operation):
    owner_id, chat_id = uuid4(), uuid4()
    repository_name = {
        'get_chat': 'get_owned_chat', 'rename_chat': 'rename_owned_chat',
        'delete_chat': 'delete_owned_chat',
    }[operation]
    repository = AsyncMock(return_value=False if operation == 'delete_chat' else None)
    monkeypatch.setattr(chat_service.chat_repository, repository_name, repository)
    session = object()
    extra = ('Title',) if operation == 'rename_chat' else ()
    with pytest.raises(chat_service.ChatNotFound):
        asyncio.run(getattr(chat_service, operation)(session, owner_id, chat_id, *extra))
    repository.assert_awaited_once_with(session, chat_id, owner_id, *extra)


def test_application_lifespan_initializes_without_database_connection(monkeypatch):
    # Engine creation is lazy; this does not attempt a connection or start a server.
    monkeypatch.setenv('PSB_DATABASE_URL', 'postgresql+asyncpg://localhost:5433/psb_knowledge_test')
    monkeypatch.setattr(app.state, 'session_factory', None, raising=False)

    async def scenario():
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.session_factory, async_sessionmaker)
    asyncio.run(scenario())


def test_api_delete_cascades_chat_data_but_preserves_knowledge(chat_api):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        foreign = await create_api_chat(other)
        async with factory.begin() as session:
            document = Document(title='Document', document_type='law', source_file='test.txt')
            session.add(document)
            await session.flush()
            version = DocumentVersion(
                document_id=document.id, version_label='v1', content_hash='a' * 64,
            )
            session.add(version)
            await session.flush()
            chunk = DocumentChunk(version_id=version.id, chunk_index=0, content='Text')
            session.add(chunk)
            message = Message(chat_id=UUID(chat['id']), role='user', content='Question')
            session.add(message)
            await session.flush()
            citation = AnswerCitation(
                message_id=message.id, chunk_id=chunk.id, position=0,
                document_title_snapshot='Document',
            )
            memory = ChatMemory(
                chat_id=message.chat_id, source_message_id=message.id,
                memory_type='context', content='Context',
            )
            session.add_all([citation, memory])
            await session.flush()
            records = [(Message, message.id), (AnswerCitation, citation.id), (ChatMemory, memory.id)]
            document_id, chunk_id = document.id, chunk.id
        response = await client.delete(f"/api/v1/chats/{chat['id']}")
        assert response.status_code == 204
        async with factory() as session:
            for model, record_id in records:
                assert await session.get(model, record_id) is None
            assert await session.get(Document, document_id) is not None
            assert await session.get(DocumentChunk, chunk_id) is not None
        assert (await other.get(f"/api/v1/chats/{foreign['id']}")).status_code == 200
    chat_api(scenario)
