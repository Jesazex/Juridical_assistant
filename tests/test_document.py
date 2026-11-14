"""Documents API: PostgreSQL, редакции и сквозная навигация из цитат."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from app.db.models import AnswerCitation, Chat, Document, DocumentChunk, DocumentVersion, Message
from app.db.repositories import document_repository, message_repository
from app.services import document_service, message_service
from tests.test_chat import chat_api, chat_database_url, create_api_chat  # noqa: F401


async def seed_document(session, title='Document', periods=((None, None),), texts=None):
    document = Document(
        title=title, document_type='law', document_number='42', source_file='document.txt',
        metadata_={'category': 'законы', 'nested': {'number': 42}},
    )
    session.add(document)
    await session.flush()
    versions = []
    for index, (begin, end) in enumerate(periods):
        version = DocumentVersion(
            document_id=document.id, version_label=f'Edition {index}', content_hash='a' * 64,
            effective_from=begin, effective_to=end, source_file=f'edition-{index}.txt',
        )
        session.add(version)
        await session.flush()
        versions.append(version)
        # Вставляем chunks в обратном порядке, чтобы проверить SQL-сортировку.
        for chunk_index, content in reversed(list(enumerate(texts or []))):
            session.add(DocumentChunk(
                version_id=version.id, chunk_index=chunk_index, content=content,
                embedding=[1.0] * 1024,
            ))
    await session.flush()
    return document, versions


def test_empty_document_list(chat_api):
    async def scenario(client, other, factory):
        response = await client.get('/api/v1/documents/')
        assert response.status_code == 200
        assert response.json() == {'items': [], 'total': 0, 'limit': 20, 'offset': 0}
        assert not response.headers.get('set-cookie')
    chat_api(scenario)


def test_document_catalog_pagination_and_sql_projection(chat_api):
    async def scenario(client, other, factory):
        async with factory.begin() as session:
            documents = [(await seed_document(session, title))[0] for title in ['B', 'A', 'A', 'C']]
        expected = sorted(documents, key=lambda document: (document.title, document.id))
        statements = []
        engine = factory.kw['bind'].engine.sync_engine

        def capture(connection, cursor, statement, params, context, many):
            statements.append(statement.lower())

        event.listen(engine, 'before_cursor_execute', capture)
        try:
            response = await client.get('/api/v1/documents/', params={'limit': 2, 'offset': 1})
        finally:
            event.remove(engine, 'before_cursor_execute', capture)
        assert response.status_code == 200
        page = response.json()
        assert (page['total'], page['limit'], page['offset']) == (4, 2, 1)
        assert [item['id'] for item in page['items']] == [str(document.id) for document in expected[1:3]]
        assert all(item['group'] == 'law' for item in page['items'])
        assert page['items'][0]['metadata']['nested'] == {'number': 42}
        assert datetime.fromisoformat(page['items'][0]['created_at']).tzinfo is not None
        assert any('limit' in statement and 'offset' in statement for statement in statements)
        assert all('embedding' not in statement for statement in statements)
        assert (await client.get('/api/v1/documents/', params={'offset': 100})).json()['items'] == []
        assert (await other.get('/api/v1/documents/')).json()['total'] == 4
        assert (await client.get('/api/v1/documents/', params={'limit': 100})).status_code == 200
    chat_api(scenario)


@pytest.mark.parametrize('params', [
    {'limit': 0}, {'limit': 101}, {'limit': 'bad'}, {'offset': -1}, {'unknown': 1},
])
def test_document_list_validation(chat_api, params):
    async def scenario(client, other, factory):
        assert (await client.get('/api/v1/documents/', params=params)).status_code == 422
    chat_api(scenario)


def test_document_detail_and_historical_version_text(chat_api):
    async def scenario(client, other, factory):
        today = datetime.now(timezone.utc).date()
        async with factory.begin() as session:
            document, versions = await seed_document(session, periods=(
                (date(2020, 1, 1), today), (today, None),
            ), texts=['First paragraph.\nShared line.', 'Shared line.\nFinal paragraph.'])
        path = f'/api/v1/documents/{document.id}'
        response = await client.get(path)
        assert response.status_code == 200
        detail = response.json()
        assert detail['document_type'] == 'law' and detail['document_number'] == '42'
        assert [version['id'] for version in detail['versions']] == [str(versions[1].id), str(versions[0].id)]
        assert detail['selection_reason'] == 'current'
        assert detail['selected_version_id'] == str(versions[1].id)
        assert detail['text'] == 'First paragraph.\nShared line.\nFinal paragraph.'
        historical = await client.get(path + f'/versions/{versions[0].id}')
        assert historical.status_code == 200
        edition = historical.json()
        assert edition['id'] == str(document.id)
        assert edition['version_id'] == str(versions[0].id)
        assert edition['version_label'] == 'Edition 0'
        assert edition['effective_to'] == today.isoformat()
        assert edition['effective_from'] == '2020-01-01'
        assert edition['source_file'] == 'edition-0.txt'
        assert edition['text'] == detail['text']
        assert 'embedding' not in historical.text and 'embedding' not in response.text
        async with factory() as session:
            chunks = await document_repository.list_version_chunks(session, versions[0].id)
            assert [chunk.chunk_index for chunk in chunks] == [0, 1]
            assert all('embedding' not in chunk.__dict__ for chunk in chunks)
    chat_api(scenario)


@pytest.mark.parametrize('periods, reason, selected', [
    ([], 'no_versions', False),
    ([(None, None)], 'single_undated', True),
    ([(None, None), (None, None)], 'ambiguous', False),
    ([(date(2020, 1, 1), None), (date(2021, 1, 1), None)], 'ambiguous', False),
    ([(date(2020, 1, 1), date(2021, 1, 1))], 'no_current', False),
    ([(date(2090, 1, 1), None)], 'no_current', False),
    ([(date(2020, 1, 1), None), (None, None)], 'ambiguous', False),
])
def test_version_selection_policy(chat_api, periods, reason, selected):
    async def scenario(client, other, factory):
        async with factory.begin() as session:
            document, versions = await seed_document(session, periods=periods, texts=['Text'])
        response = await client.get(f'/api/v1/documents/{document.id}')
        assert response.status_code == 200
        detail = response.json()
        assert detail['selection_reason'] == reason
        assert detail['selected_version_id'] == (str(versions[0].id) if selected else None)
        assert detail['text'] == ('Text' if selected else None)
        assert len(detail['versions']) == len(periods)
    chat_api(scenario)


def test_empty_version_and_source_file_fallback(chat_api):
    async def scenario(client, other, factory):
        async with factory.begin() as session:
            document, versions = await seed_document(session)
            versions[0].source_file = None
        response = await client.get(f'/api/v1/documents/{document.id}/versions/{versions[0].id}')
        assert response.status_code == 200
        assert response.json()['text'] == ''
        assert response.json()['source_file'] == 'document.txt'
    chat_api(scenario)


def test_missing_document_and_wrong_version(chat_api):
    async def scenario(client, other, factory):
        async with factory.begin() as session:
            document, versions = await seed_document(session)
            foreign, foreign_versions = await seed_document(session, 'Other')
        assert (await client.get(f'/api/v1/documents/{uuid4()}')).status_code == 404
        assert (await client.get(f'/api/v1/documents/{uuid4()}/versions/{versions[0].id}')).status_code == 404
        path = f'/api/v1/documents/{document.id}/versions/'
        missing = await client.get(path + str(uuid4()))
        wrong = await client.get(path + str(foreign_versions[0].id))
        assert missing.status_code == wrong.status_code == 404
        assert missing.json() == wrong.json() == {'detail': 'Document version not found'}
    chat_api(scenario)


@pytest.mark.parametrize('path', [
    '/api/v1/documents/not-uuid',
    f'/api/v1/documents/{uuid4()}/versions/not-uuid',
    f'/api/v1/documents/not-uuid/versions/{uuid4()}',
])
def test_document_uuid_validation(chat_api, path):
    async def scenario(client, other, factory):
        assert (await client.get(path)).status_code == 422
    chat_api(scenario)


@pytest.mark.parametrize('contents, expected', [
    ([], ''),
    (['First', 'Second'], 'First\n\nSecond'),
    (['A\nShared', 'Shared\nB'], 'A\nShared\nB'),
    (['First contract', 'contract terms'], 'First contract\n\ncontract terms'),
    (['A\nB', 'A\nB'], 'A\nB'),
    (['Start ' + 'long overlap ' * 10, 'long overlap ' * 10 + 'end'], 'Start ' + 'long overlap ' * 10 + 'end'),
])
def test_merge_chunk_boundaries(contents, expected):
    assert document_repository.merge_chunk_texts(contents) == expected


def test_service_has_no_orm_dependency_and_raises_domain_errors(monkeypatch):
    import asyncio

    monkeypatch.setattr(document_repository, 'get_document', AsyncMock(return_value=None))
    with pytest.raises(document_service.DocumentNotFound):
        asyncio.run(document_service.get_document(object(), uuid4()))


def test_message_source_opens_exact_historical_version(chat_api, monkeypatch):
    async def scenario(client, other, factory):
        monkeypatch.setattr(message_service, 'process_pending_answer', AsyncMock())
        chat = await create_api_chat(client)
        path = f"/api/v1/chats/{chat['id']}/messages/"
        exchange = (await client.post(path, json={'content': 'Question'})).json()
        async with factory.begin() as session:
            document, versions = await seed_document(session, periods=(
                (date(2020, 1, 1), date(2021, 1, 1)), (date(2021, 1, 1), None),
            ))
            chunk = DocumentChunk(version_id=versions[0].id, chunk_index=0, content='Historical answer text')
            session.add(chunk)
            session.add(DocumentChunk(version_id=versions[1].id, chunk_index=0, content='Current text'))
            await session.flush()
            owner_id = (await session.get(Chat, UUID(chat['id']))).owner_id
            await message_repository.complete_answer(
                session, UUID(chat['id']), owner_id, UUID(exchange['assistant_message']['id']), 'Answer',
                attempt_started_at=datetime.fromisoformat(exchange['assistant_message']['updated_at']),
                citations=[chunk.id],
            )
        sources = (await client.get(path)).json()['items'][1]['sources']
        assert sources[0]['document_id'] == str(document.id)
        assert sources[0]['version_id'] == str(versions[0].id)
        assert sources[0]['chunk_id'] == str(chunk.id)
        version = await client.get(
            f"/api/v1/documents/{sources[0]['document_id']}/versions/{sources[0]['version_id']}",
        )
        assert version.status_code == 200 and version.json()['text'] == 'Historical answer text'
        assert (await client.get(f'/api/v1/documents/{document.id}')).json()['text'] == 'Current text'
        assert (await other.get(path)).status_code == 404
        # Сохраняем snapshot, даже если связь с chunk больше не существует.
        async with factory.begin() as session:
            citation = await session.scalar(select(AnswerCitation).where(AnswerCitation.chunk_id == chunk.id))
            citation.chunk_id = None
        source = (await client.get(path)).json()['items'][1]['sources'][0]
        assert source['version_id'] is None and source['excerpt'] == 'Historical answer text'
    chat_api(scenario)
