"""DeepSeek tests use mock HTTP transports and isolated settings, never real keys."""

import asyncio
import json
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from app import main as application_module
from app.core import config
from app.llm.deepseec_coonection import ChatMessage, DeepSeekClient
from app.llm.deepseec_exseptions import (
    DeepSeekAuthenticationError,
    DeepSeekEmptyResponseError,
    DeepSeekHTTPError,
    DeepSeekInvalidJSONError,
    DeepSeekInvalidResponseError,
    DeepSeekNetworkError,
    DeepSeekRateLimitError,
    DeepSeekServerError,
    DeepSeekTimeoutError,
)

API_KEY = "test-secret-never-a-real-key"
MODEL = "test-model"
MESSAGES: tuple[ChatMessage, ...] = (
    {"role": "system", "content": "Test instructions"},
    {"role": "user", "content": "Первый вопрос"},
    {"role": "assistant", "content": "Предыдущий ответ"},
    {"role": "user", "content": "Уточнение"},
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    for name in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    return env_file


@pytest.fixture
def configured_deepseek(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.test/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", API_KEY)
    monkeypatch.setenv("DEEPSEEK_MODEL", MODEL)
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", "12.5")


def generate(respond, **options):
    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://deepseek.test/v1/",
            headers={"Authorization": f"Bearer {API_KEY}"},
            transport=httpx.MockTransport(respond),
        ) as http_client:
            client = DeepSeekClient(http_client, MODEL)
            assert client.http_client is http_client
            assert client.model == MODEL
            answer = await client.generate(MESSAGES, **options)
            assert not http_client.is_closed  # The component must not close its caller's client.
            return answer
    return asyncio.run(scenario())


def test_successful_generation_preserves_request_and_extracts_first_answer():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url == "https://deepseek.test/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert json.loads(request.content) == {
            "model": MODEL, "messages": list(MESSAGES), "stream": False,
        }
        return httpx.Response(200, json={"choices": [
            {"message": {"role": "assistant", "content": "Ответ\n\nС пояснением.\n"}},
            {"message": {"content": "Another choice"}},
        ]})

    assert generate(respond) == "Ответ\n\nС пояснением.\n"
    assert len(requests) == 1


@pytest.mark.parametrize("options", [
    {"temperature": 0}, {"max_tokens": 128}, {"temperature": 0.3, "max_tokens": 256},
])
def test_optional_parameters_are_only_sent_when_requested(options):
    def respond(request):
        assert json.loads(request.content) == {
            "model": MODEL, "messages": list(MESSAGES), "stream": False, **options,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})
    assert generate(respond, **options) == "Answer"


@pytest.mark.parametrize("status, error", [
    (401, DeepSeekAuthenticationError), (403, DeepSeekAuthenticationError),
    (429, DeepSeekRateLimitError), (500, DeepSeekServerError), (503, DeepSeekServerError),
    (400, DeepSeekHTTPError), (302, DeepSeekHTTPError),
])
def test_http_errors_are_typed_safe_and_not_retried(status, error, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": API_KEY}})

    with caplog.at_level("DEBUG"), pytest.raises(error) as caught:
        generate(respond)
    assert caught.value.status_code == status
    assert str(status) in str(caught.value)
    assert API_KEY not in "".join(traceback.format_exception(caught.value))
    assert API_KEY not in caplog.text
    assert len(requests) == 1


@pytest.mark.parametrize("transport_error, error", [
    (httpx.ReadTimeout, DeepSeekTimeoutError),
    (httpx.ConnectTimeout, DeepSeekTimeoutError),
    (httpx.PoolTimeout, DeepSeekTimeoutError),
    (httpx.ConnectError, DeepSeekNetworkError),
    (httpx.ReadError, DeepSeekNetworkError),
    (httpx.RemoteProtocolError, DeepSeekNetworkError),
])
def test_transport_errors_are_typed_safe_and_not_retried(transport_error, error, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        raise transport_error(API_KEY, request=request)

    with caplog.at_level("DEBUG"), pytest.raises(error) as caught:
        generate(respond)
    assert API_KEY not in "".join(traceback.format_exception(caught.value))
    assert API_KEY not in caplog.text
    assert len(requests) == 1


def test_invalid_json_is_sanitized():
    with pytest.raises(DeepSeekInvalidJSONError) as caught:
        generate(lambda request: httpx.Response(200, text=API_KEY))
    assert API_KEY not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("payload", [
    None, [], {}, {"choices": None}, {"choices": []}, {"choices": {}},
    {"choices": [None]}, {"choices": [{}]}, {"choices": [{"message": None}]},
    {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": 123}}]},
    {"choices": [{"message": {"content": ["Answer"]}}]},
])
def test_invalid_response_structure(payload):
    with pytest.raises(DeepSeekInvalidResponseError):
        generate(lambda request: httpx.Response(200, content=json.dumps(payload)))


@pytest.mark.parametrize("content", [None, "", " \t\n "])
def test_empty_model_answer(content):
    with pytest.raises(DeepSeekEmptyResponseError):
        generate(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
        }))


@pytest.mark.parametrize("options", [
    {"temperature": -1}, {"temperature": 3}, {"temperature": float("nan")},
    {"max_tokens": 0}, {"max_tokens": 1.5}, {"max_tokens": True},
])
def test_invalid_optional_parameters_do_not_send_requests(options):
    respond = Mock(side_effect=AssertionError("HTTP must not be called"))
    with pytest.raises(ValueError):
        generate(respond, **options)
    respond.assert_not_called()


def test_reads_dotenv_without_interpolation_or_environment_mutation(isolated_settings, monkeypatch):
    isolated_settings.write_text(
        'DEEPSEEK_BASE_URL=https://dotenv.test/v1\n'
        'DEEPSEEK_API_KEY="test-${UNCHANGED}-key"\n'
        'DEEPSEEK_MODEL=model-from-dotenv\nDEEPSEEK_TIMEOUT=15\n', encoding="utf-8",
    )
    monkeypatch.setenv("UNCHANGED", "must-not-be-interpolated")
    # Loading must remain independent of the process's working directory.
    other_directory = isolated_settings.parent / "elsewhere"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)
    settings = config.get_deepseek_settings()
    assert settings.is_configured
    assert settings.base_url == "https://dotenv.test/v1"
    assert settings.api_key == "test-${UNCHANGED}-key"
    assert settings.model == "model-from-dotenv"
    assert settings.timeout == 15
    assert settings.api_key not in repr(settings)
    assert "DEEPSEEK_API_KEY" not in config.os.environ


def test_environment_overrides_dotenv(isolated_settings, configured_deepseek):
    isolated_settings.write_text(
        "DEEPSEEK_BASE_URL=https://dotenv.test\nDEEPSEEK_API_KEY=file-key\n"
        "DEEPSEEK_MODEL=file-model\nDEEPSEEK_TIMEOUT=99\n", encoding="utf-8",
    )
    settings = config.get_deepseek_settings()
    assert settings.base_url == "https://deepseek.test/v1"
    assert settings.api_key == API_KEY
    assert settings.model == MODEL
    assert settings.timeout == 12.5


def test_missing_api_key_disables_client_without_reusing_embedding_credentials(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.test")
    monkeypatch.setenv("DEEPSEEK_MODEL", MODEL)
    monkeypatch.setenv("LLM_BASE_URL", "https://embedding.test")
    monkeypatch.setenv("LLM_API_KEY", "embedding-only-key")
    settings = config.get_deepseek_settings()
    assert settings.api_key == ""
    assert settings.missing_parameters == ("DEEPSEEK_API_KEY",)
    assert not settings.is_configured
    assert settings.timeout == 60


def test_empty_environment_key_overrides_configured_dotenv(isolated_settings, monkeypatch):
    isolated_settings.write_text(
        f"DEEPSEEK_BASE_URL=https://deepseek.test\nDEEPSEEK_API_KEY={API_KEY}\n"
        f"DEEPSEEK_MODEL={MODEL}\n", encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    assert not config.get_deepseek_settings().is_configured


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", API_KEY])
def test_invalid_timeout_does_not_expose_setting_values(monkeypatch, configured_deepseek, value):
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", value)
    with pytest.raises(config.DeepSeekConfigurationError) as caught:
        config.get_deepseek_settings()
    assert API_KEY not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("url", [
    "not-a-url", "https://", "ftp://deepseek.test", "https://deepseek.test:invalid",
    f"https://user:{API_KEY}@deepseek.test", f"https://deepseek.test?key={API_KEY}",
])
def test_invalid_base_url_does_not_expose_credentials(monkeypatch, configured_deepseek, url):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    with pytest.raises(config.DeepSeekConfigurationError) as caught:
        config.get_deepseek_settings()
    assert API_KEY not in "".join(traceback.format_exception(caught.value))


@pytest.fixture
def lifespan_application(monkeypatch):
    engine = SimpleNamespace(dispose=AsyncMock())
    session_factory = object()
    monkeypatch.setattr(application_module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(application_module, "create_session_factory", lambda unused: session_factory)
    return FastAPI(lifespan=application_module.lifespan), engine, session_factory


@pytest.mark.parametrize("missing", [None, "DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"])
def test_lifespan_without_required_setting_starts_without_http(
    monkeypatch, configured_deepseek, lifespan_application, missing, caplog,
):
    missing_parameters = (missing,) if missing else (
        "DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL",
    )
    for name in missing_parameters:
        monkeypatch.delenv(name)
    # An inactive provider must not stop startup even if unused options are invalid.
    monkeypatch.setenv("DEEPSEEK_TIMEOUT", "unused-invalid-timeout")
    application, engine, session_factory = lifespan_application
    constructor = Mock(side_effect=AssertionError("HTTP client must not be created"))
    monkeypatch.setattr(application_module.httpx, "AsyncClient", constructor)

    async def scenario():
        async with application.router.lifespan_context(application):
            assert application.state.deepseek_client is None
            assert application.state.session_factory is session_factory
    asyncio.run(scenario())
    constructor.assert_not_called()
    engine.dispose.assert_awaited_once()
    assert "disabled" in caplog.text
    assert all(name in caplog.text for name in missing_parameters)
    assert API_KEY not in caplog.text


@pytest.fixture
def mock_lifespan_http(monkeypatch):
    real_http_client = httpx.AsyncClient
    requests = []
    clients = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})

    def create_client(**kwargs):
        client = real_http_client(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    constructor = Mock(side_effect=create_client)
    monkeypatch.setattr(application_module.httpx, "AsyncClient", constructor)
    return constructor, clients, requests


def test_lifespan_reuses_configured_client_and_closes_resources(
    configured_deepseek, lifespan_application, mock_lifespan_http,
):
    application, engine, session_factory = lifespan_application
    constructor, clients, requests = mock_lifespan_http

    async def scenario():
        async with application.router.lifespan_context(application):
            client = application.state.deepseek_client
            assert isinstance(client, DeepSeekClient)
            assert client.model == MODEL
            assert application.state.session_factory is session_factory
            assert not requests  # Startup must never contact the provider.
            assert await client.generate(MESSAGES) == "Answer"
            assert await client.generate(MESSAGES) == "Answer"
            assert client.http_client is clients[0] and not clients[0].is_closed
        assert application.state.deepseek_client is None
        assert clients[0].is_closed
    asyncio.run(scenario())
    constructor.assert_called_once()
    engine.dispose.assert_awaited_once()
    assert len(requests) == 2
    for request in requests:
        assert request.url == "https://deepseek.test/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert set(request.extensions["timeout"].values()) == {12.5}


@pytest.mark.parametrize("failure_stage", [
    "session_factory", "settings", "http_client", "deepseek_client", "running",
])
def test_lifespan_cleans_resources_on_initialization_and_runtime_errors(
    monkeypatch, configured_deepseek, lifespan_application, mock_lifespan_http, failure_stage,
):
    application, engine, _ = lifespan_application
    constructor, clients, requests = mock_lifespan_http
    if failure_stage == "session_factory":
        monkeypatch.setattr(application_module, "create_session_factory", Mock(side_effect=RuntimeError("test")))
    elif failure_stage == "settings":
        monkeypatch.setattr(application_module, "get_deepseek_settings", Mock(side_effect=RuntimeError("test")))
    elif failure_stage == "http_client":
        constructor.side_effect = RuntimeError("test")
    elif failure_stage == "deepseek_client":
        monkeypatch.setattr(application_module, "DeepSeekClient", Mock(side_effect=RuntimeError("test")))

    async def scenario():
        async with application.router.lifespan_context(application):
            raise RuntimeError("test")

    with pytest.raises(RuntimeError, match="test"):
        asyncio.run(scenario())
    engine.dispose.assert_awaited_once()
    assert all(client.is_closed for client in clients)
    assert application.state.deepseek_client is None
    assert not requests
    assert constructor.call_count == (1 if failure_stage in {"http_client", "deepseek_client", "running"} else 0)


def test_lifespan_disposes_engine_even_if_http_close_fails(
    monkeypatch, configured_deepseek, lifespan_application,
):
    application, engine, _ = lifespan_application
    http_client = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    monkeypatch.setattr(application_module.httpx, "AsyncClient", Mock(return_value=http_client))

    async def scenario():
        async with application.router.lifespan_context(application):
            assert application.state.deepseek_client is not None
    with pytest.raises(RuntimeError, match="close failed"):
        asyncio.run(scenario())
    http_client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert application.state.deepseek_client is None
