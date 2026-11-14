"""Origin/CORS и cookie за доверенным прокси; записи проверяются в PostgreSQL."""

from contextlib import asynccontextmanager
from pathlib import Path
import runpy
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.security import ANONYMOUS_COOKIE, token_hash
from app.db.models import AnonymousUser, Chat
from app.main import DEFAULT_CORS_ORIGINS, configured_origins
from tests.test_chat import chat_api, chat_database_url  # noqa: F401

PROXY_IP = '172.30.80.2'


@pytest.fixture
def configured_app(monkeypatch):
    def create(origins='', secure=False):
        monkeypatch.setenv('PSB_CORS_ORIGINS', origins)
        monkeypatch.setenv('PSB_COOKIE_SECURE', str(secure).lower())
        # Новый экземпляр читает startup-конфигурацию, не меняя app других тестов.
        return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app/main.py'))['app']
    return create


@asynccontextmanager
async def origin_client(application, factory, *, base_url='http://api.internal', peer='203.0.113.10'):
    application.state.session_factory = factory
    proxied = ProxyHeadersMiddleware(application, trusted_hosts=PROXY_IP)
    transport = httpx.ASGITransport(app=proxied, client=(peer, 12345))
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        yield client


@pytest.mark.parametrize('origin', sorted(DEFAULT_CORS_ORIGINS))
@pytest.mark.parametrize('body', [{}, {'title': '  Named chat  '}])
def test_local_origin_creates_persisted_chat_and_cookie(chat_api, configured_app, origin, body):
    application = configured_app()

    async def scenario(unused, other, factory):
        async with origin_client(application, factory) as client:
            response = await client.post('/api/v1/chats/', json=body, headers={'Origin': origin})
            assert response.status_code == 201, response.text
            assert response.headers['access-control-allow-origin'] == origin
            assert response.headers['access-control-allow-credentials'] == 'true'
            cookie = response.headers['set-cookie'].lower()
            assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/' in cookie
            assert 'max-age=2592000' in cookie and 'secure' not in cookie
            assert 'domain=' not in cookie
            async with factory() as session:
                chat = await session.get(Chat, UUID(response.json()['id']))
                owner = await session.scalar(select(AnonymousUser).where(
                    AnonymousUser.token_hash == token_hash(client.cookies[ANONYMOUS_COOKIE]),
                ))
                assert chat.owner_id == owner.id
                assert chat.is_title_custom is ('title' in body)
                assert chat.title == ('Named chat' if body else 'Новый чат')
            assert (await client.get('/api/v1/chats/')).json()['total'] == 1
    chat_api(scenario)


def test_existing_cookie_preserves_owner_on_second_post(chat_api, configured_app):
    application = configured_app()

    async def scenario(unused, other, factory):
        async with origin_client(application, factory, base_url='http://localhost:8080') as client:
            first = await client.post('/api/v1/chats/', json={}, headers={'Origin': 'http://localhost:8080'})
            assert first.status_code == 201
            original_cookie = client.cookies[ANONYMOUS_COOKIE]
            second = await client.post('/api/v1/chats/', json={'title': 'Second'}, headers={'Origin': 'http://localhost:8080'})
            assert second.status_code == 201
            assert 'set-cookie' not in second.headers
            assert client.cookies[ANONYMOUS_COOKIE] == original_cookie
            async with factory() as session:
                chats = list(await session.scalars(select(Chat).where(Chat.id.in_(
                    [UUID(first.json()['id']), UUID(second.json()['id'])],
                ))))
                assert len(chats) == 2 and chats[0].owner_id == chats[1].owner_id
                assert await session.scalar(select(func.count()).select_from(AnonymousUser)) == 1
    chat_api(scenario)


def test_production_origin_and_secure_cookie_from_environment(chat_api, configured_app):
    origin = 'https://legal.example'
    application = configured_app(origins=origin, secure=True)

    async def scenario(unused, other, factory):
        # Отдельный API origin подтверждает использование allowlist, а не same-origin bypass.
        async with origin_client(application, factory, base_url='https://api.example') as client:
            headers = {'Origin': origin}
            preflight = await client.options('/api/v1/chats/', headers={
                **headers, 'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            })
            assert preflight.status_code == 200
            assert preflight.headers['access-control-allow-origin'] == origin
            assert preflight.headers['access-control-allow-credentials'] == 'true'
            created = await client.post('/api/v1/chats/', json={}, headers=headers)
            assert created.status_code == 201
            assert created.headers['access-control-allow-origin'] == origin
            assert 'secure' in created.headers['set-cookie'].lower()
            fetched = await client.get(f"/api/v1/chats/{created.json()['id']}", headers=headers)
            assert fetched.status_code == 200 and fetched.json() == created.json()
    chat_api(scenario)


@pytest.mark.parametrize('origin', ['https://evil.example', 'null', 'http://localhost:8080.evil.example'])
def test_disallowed_origin_does_not_write_or_set_cookie(chat_api, configured_app, origin):
    application = configured_app()

    async def scenario(unused, other, factory):
        async with origin_client(application, factory) as client:
            response = await client.post('/api/v1/chats/', json={}, headers={'Origin': origin})
            assert response.status_code == 403
            assert response.json() == {'detail': 'Request origin is not allowed'}
            assert 'set-cookie' not in response.headers
            assert 'access-control-allow-origin' not in response.headers
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(Chat)) == 0
                assert await session.scalar(select(func.count()).select_from(AnonymousUser)) == 0
    chat_api(scenario)


@pytest.mark.parametrize('fetch_site', ['cross-site', 'same-site'])
def test_cross_site_write_without_origin_still_rejected(chat_api, configured_app, fetch_site):
    application = configured_app()

    async def scenario(unused, other, factory):
        async with origin_client(application, factory) as client:
            response = await client.post('/api/v1/chats/', json={}, headers={'Sec-Fetch-Site': fetch_site})
            assert response.status_code == 403 and 'set-cookie' not in response.headers
    chat_api(scenario)


@pytest.mark.parametrize('peer, status', [(PROXY_IP, 201), ('203.0.113.10', 403)])
def test_only_trusted_proxy_can_supply_https_scheme(chat_api, configured_app, peer, status):
    # Этот origin отсутствует в allowlist: разрешение требует корректного same-origin.
    application = configured_app(origins='https://another-frontend.example')

    async def scenario(unused, other, factory):
        async with origin_client(application, factory, base_url='http://public.example', peer=peer) as client:
            response = await client.post('/api/v1/chats/', json={}, headers={
                'Origin': 'https://public.example', 'X-Forwarded-Proto': 'https',
            })
            assert response.status_code == status
            if status == 201:
                # Secure автоматически выставляется по доверенной схеме даже при flag=false.
                assert 'secure' in response.headers['set-cookie'].lower()
                async with factory() as session:
                    assert await session.get(Chat, UUID(response.json()['id'])) is not None
            else:
                assert 'set-cookie' not in response.headers
    chat_api(scenario)


def test_forged_forwarded_host_and_proto_do_not_override_direct_request(chat_api, configured_app):
    application = configured_app(origins='https://configured.example')

    async def scenario(unused, other, factory):
        async with origin_client(application, factory, base_url='http://public.example') as client:
            headers = {'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'evil.example'}
            rejected = await client.post('/api/v1/chats/', json={}, headers={**headers, 'Origin': 'https://evil.example'})
            assert rejected.status_code == 403
            accepted = await client.post('/api/v1/chats/', json={}, headers={**headers, 'Origin': 'http://public.example'})
            assert accepted.status_code == 201
            assert 'secure' not in accepted.headers['set-cookie'].lower()
    chat_api(scenario)


@pytest.mark.parametrize('secure', [False, True])
def test_cookie_secure_flag_is_configurable_on_http(chat_api, configured_app, secure):
    application = configured_app(secure=secure)

    async def scenario(unused, other, factory):
        async with origin_client(application, factory) as client:
            response = await client.post('/api/v1/chats/', json={})
            assert response.status_code == 201
            assert ('secure' in response.headers['set-cookie'].lower()) is secure
    chat_api(scenario)


def test_production_allowlist_replaces_local_defaults(monkeypatch):
    monkeypatch.setenv('PSB_CORS_ORIGINS', ' https://legal.example,https://staff.example/ ')
    assert configured_origins() == {'https://legal.example', 'https://staff.example'}


@pytest.mark.parametrize('value', ['', '   '])
def test_missing_origins_use_explicit_local_defaults(monkeypatch, value):
    monkeypatch.setenv('PSB_CORS_ORIGINS', value)
    assert configured_origins() == DEFAULT_CORS_ORIGINS


@pytest.mark.parametrize('value', ['*', 'https://*.example', 'null', 'https://example.com/path', 'https://user@example.com'])
def test_invalid_origin_configuration_rejected(monkeypatch, value):
    monkeypatch.setenv('PSB_CORS_ORIGINS', value)
    with pytest.raises(ValueError, match='explicit HTTP'):
        configured_origins()
