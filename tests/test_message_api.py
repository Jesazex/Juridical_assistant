"""Message API integration tests on the guarded, separate PostgreSQL test DB."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import ANONYMOUS_COOKIE, token_hash
from app.db.models import AnonymousUser, AnswerCitation, Chat, Message
from app.db.repositories import message_repository
from app.db.session import create_database_engine, create_session_factory
from app.main import app
from app.services import message_service
from tests.test_chat import chat_api, chat_database_url, create_api_chat  # noqa: F401


def messages_path(chat):
    return f"/api/v1/chats/{chat['id']}/messages/"


async def send(client, path, content='Question'):
    response = await client.post(path, json={'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_history_and_pagination(chat_api):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        empty = await client.get(path)
        assert empty.status_code == 200
        assert empty.json() == {'items': [], 'total': 0, 'limit': 50, 'offset': 0}
        for index in range(3):
            await send(client, path, str(index))
        full = (await client.get(path)).json()
        assert full['total'] == 6
        assert [item['role'] for item in full['items']] == ['user', 'assistant'] * 3
        page = (await client.get(path, params={'limit': 2, 'offset': 1})).json()
        assert page == {'items': full['items'][1:3], 'total': 6, 'limit': 2, 'offset': 1}
        assert (await client.get(path, params={'offset': 99})).json()['items'] == []
        assert (await client.get(path, params={'limit': 100})).status_code == 200
    chat_api(scenario)


def test_send_pending_response_and_background_failure(chat_api):
    async def scenario(client, other, factory):
        chat = await create_api_chat(client)
        path = messages_path(chat)
        exchange = await send(client, path, '  Question  ')
        assert set(exchange) == {'user_message', 'assistant_message'}
        user, answer = exchange['user_message'], exchange['assistant_message']
        assert user['role'] == 'user' and user['status'] == 'completed'
        assert user['content'] == 'Question' and user['reply_to_message_id'] is None
        assert answer['role'] == 'assistant' and answer['status'] == 'pending'
        assert answer['reply_to_message_id'] == user['id']
        assert answer['content'] == '' and answer['error_code'] is None
        assert user['sources'] == answer['sources'] == []
        assert user['chat_id'] == answer['chat_id'] == chat['id']
        stored = (await client.get(path)).json()['items']
        assert stored[0] == user
        assert stored[1]['status'] == 'failed'
        assert stored[1]['error_code'] == 'generation_unavailable'
        assert datetime.fromisoformat(stored[1]['updated_at']) > datetime.fromisoformat(answer['updated_at'])
        async with factory() as session:
            rows = list(await session.scalars(select(Message).where(Message.chat_id == UUID(chat['id']))))
            assert len(rows) == 2
            assert next(row for row in rows if row.role == 'user').status is None
    chat_api(scenario)


@pytest.mark.parametrize('method', ['GET', 'POST', 'retry'])
def test_foreign_and_missing_chat_are_404(chat_api, method):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        exchange = await send(client, path)
        for target in (path, f'/api/v1/chats/{uuid4()}/messages/'):
            if method == 'retry':
                response = await other.post(target + exchange['assistant_message']['id'] + '/retry')
            else:
                options = {'json': {'content': 'stolen'}} if method == 'POST' else {}
                response = await other.request(method, target, **options)
            assert response.status_code == 404
        assert (await client.get(path)).json()['total'] == 2
    chat_api(scenario)


@pytest.mark.parametrize('content', ['', ' \t\n ', 'x' * 10_001, None, 123])
def test_invalid_content_does_not_write(chat_api, content):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        assert (await client.post(path, json={'content': content})).status_code == 422
        assert (await client.get(path)).json()['total'] == 0
    chat_api(scenario)


def test_maximum_content(chat_api):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        assert (await send(client, path, 'x' * 10_000))['user_message']['content'] == 'x' * 10_000
    chat_api(scenario)


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 101}, {'offset': -1}, {'limit': 'bad'}, {'owner_id': str(uuid4())}])
def test_invalid_pagination(chat_api, params):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        assert (await client.get(path, params=params)).status_code == 422
    chat_api(scenario)


def test_retry_failed_reuses_answer_and_runs_background(chat_api):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        exchange = await send(client, path)
        answer = exchange['assistant_message']
        response = await client.post(path + answer['id'] + '/retry')
        assert response.status_code == 200, response.text
        retried = response.json()
        assert retried['id'] == answer['id']
        assert retried['reply_to_message_id'] == exchange['user_message']['id']
        assert retried['status'] == 'pending' and retried['error_code'] is None
        assert retried['updated_at'] > answer['updated_at']
        history = (await client.get(path)).json()
        assert history['total'] == 2
        assert history['items'][1]['status'] == 'failed'
        assert history['items'][1]['error_code'] == 'generation_unavailable'
    chat_api(scenario)


@pytest.mark.parametrize('status', ['pending', 'completed', 'user'])
def test_retry_rejects_non_failed_answers(chat_api, monkeypatch, status):
    async def scenario(client, other, factory):
        monkeypatch.setattr(message_service, 'process_pending_answer', AsyncMock())
        chat = await create_api_chat(client)
        path = messages_path(chat)
        exchange = await send(client, path)
        answer = exchange['assistant_message']
        target_id = answer['id']
        if status == 'completed':
            async with factory.begin() as session:
                owner_id = (await session.get(Chat, UUID(chat['id']))).owner_id
                await message_repository.complete_answer(
                    session, UUID(chat['id']), owner_id, UUID(answer['id']), 'Answer',
                    attempt_started_at=datetime.fromisoformat(answer['updated_at']),
                )
        elif status == 'user':
            target_id = exchange['user_message']['id']
        response = await client.post(path + target_id + '/retry')
        assert response.status_code == 409
        assert message_service.process_pending_answer.await_count == 1
        assert (await client.get(path)).json()['total'] == 2
    chat_api(scenario)


def test_retry_already_started_does_not_schedule_duplicate(chat_api, monkeypatch):
    original = message_repository.create_pending_answer

    async def already_started(*args):
        await original(*args)
        return await original(*args)

    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        exchange = await send(client, path)
        handler = AsyncMock()
        monkeypatch.setattr(message_service, 'process_pending_answer', handler)
        monkeypatch.setattr(message_repository, 'create_pending_answer', already_started)
        response = await client.post(path + exchange['assistant_message']['id'] + '/retry')
        assert response.status_code == 409
        handler.assert_not_awaited()
        assert (await client.get(path)).json()['total'] == 2
    chat_api(scenario)


def test_missing_and_wrong_chat_message_are_404(chat_api):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        exchange = await send(client, path)
        other_path = messages_path(await create_api_chat(client))
        assert (await client.post(path + str(uuid4()) + '/retry')).status_code == 404
        assert (await client.post(other_path + exchange['assistant_message']['id'] + '/retry')).status_code == 404
    chat_api(scenario)


@pytest.mark.parametrize('error, status', [(RuntimeError, 500), (SQLAlchemyError, 503)])
def test_failed_send_rolls_back_and_does_not_schedule(chat_api, monkeypatch, error, status):
    async def scenario(client, other, factory):
        path = messages_path(await create_api_chat(client))
        handler = AsyncMock()
        monkeypatch.setattr(message_service, 'process_pending_answer', handler)
        monkeypatch.setattr(message_repository, 'create_pending_answer', AsyncMock(side_effect=error('test')))
        assert (await client.post(path, json={'content': 'Question'})).status_code == status
        assert (await client.get(path)).json()['total'] == 0
        handler.assert_not_awaited()
    chat_api(scenario)


def test_background_uses_new_session_and_stale_attempt_is_ignored(chat_api, monkeypatch):
    original = message_service.process_pending_answer
    handler = AsyncMock()

    async def scenario(client, other, factory):
        monkeypatch.setattr(message_service, 'process_pending_answer', handler)
        chat = await create_api_chat(client)
        path = messages_path(chat)
        exchange = await send(client, path)
        args = handler.call_args.args
        assert args[0] is factory
        # The handler opens a different session and sees the committed pending row.
        await original(*args)
        assert (await client.get(path)).json()['items'][1]['status'] == 'failed'
        retry = await client.post(path + exchange['assistant_message']['id'] + '/retry')
        assert retry.status_code == 200
        await original(*args)  # Old timestamp must not fail the new pending attempt.
        current = (await client.get(path)).json()['items'][1]
        assert current['status'] == 'pending' and current['error_code'] is None
        await original(*handler.call_args.args)
        assert (await client.get(path)).json()['items'][1]['status'] == 'failed'
    chat_api(scenario)


def test_completed_answer_sources(chat_api, monkeypatch):
    async def scenario(client, other, factory):
        monkeypatch.setattr(message_service, 'process_pending_answer', AsyncMock())
        path = messages_path(await create_api_chat(client))
        exchange = await send(client, path)
        async with factory.begin() as session:
            answer = await session.get(Message, UUID(exchange['assistant_message']['id']))
            answer.status, answer.content = 'completed', 'Answer'
            session.add(AnswerCitation(
                message_id=answer.id, position=0, document_title_snapshot='Law',
                excerpt_snapshot='Source text', document_id_snapshot='document-id',
            ))
        response = (await client.get(path)).json()['items'][1]
        assert response['status'] == 'completed'
        assert response['sources'][0]['document_title'] == 'Law'
        assert response['sources'][0]['excerpt'] == 'Source text'
    chat_api(scenario)


def test_committed_attempt_and_concurrent_retry(chat_database_url, monkeypatch):
    """Use separate physical connections to check commit visibility and row locks."""
    original = message_service.process_pending_answer

    async def scenario():
        engine = create_database_engine(chat_database_url)
        factory = create_session_factory(engine)
        monkeypatch.setitem(app.state._state, 'session_factory', factory)
        monkeypatch.setitem(app.state._state, 'cookie_secure', False)
        observed = []

        async def process(factory, owner_id, chat_id, message_id, started_at):
            async with factory() as session:
                message = await session.get(Message, message_id)
                assert message is not None and message.status == 'pending'
                assert message.updated_at == started_at
                observed.append(message.id)
                # Keep this connection checked out while the handler opens its own.
                await original(factory, owner_id, chat_id, message_id, started_at)

        monkeypatch.setattr(message_service, 'process_pending_answer', process)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            try:
                chat = await create_api_chat(client)
                path = messages_path(chat)
                exchange = await send(client, path)
                answer_id = exchange['assistant_message']['id']
                assert observed == [UUID(answer_id)]
                assert (await client.get(path)).json()['items'][1]['status'] == 'failed'
                handler = AsyncMock()
                monkeypatch.setattr(message_service, 'process_pending_answer', handler)
                responses = await asyncio.gather(
                    client.post(path + answer_id + '/retry'),
                    client.post(path + answer_id + '/retry'),
                )
                assert sorted(response.status_code for response in responses) == [200, 409]
                handler.assert_awaited_once()
                history = (await client.get(path)).json()
                assert history['total'] == 2 and history['items'][1]['status'] == 'pending'
            finally:
                # Delete only this scenario's owner; FK cascades remove its chat/messages.
                cookie = client.cookies.get(ANONYMOUS_COOKIE)
                if cookie:
                    async with factory.begin() as session:
                        await session.execute(delete(AnonymousUser).where(
                            AnonymousUser.token_hash == token_hash(cookie),
                        ))
                await engine.dispose()

    asyncio.run(scenario())
