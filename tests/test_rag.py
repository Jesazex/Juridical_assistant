import asyncio

import httpx
import pytest

from app.rag.common.embeddings import EmbeddingError, embed_texts, validate_embedding


@pytest.mark.parametrize("vector", [[1, 2], [0] * 1024, [float("nan")] * 1024, [True] * 1024])
def test_rejects_invalid_embedding(vector):
    with pytest.raises(ValueError):
        validate_embedding(vector)


@pytest.mark.parametrize("second_index", [0, 1])
def test_embedding_response_indices(monkeypatch, second_index):
    monkeypatch.setenv("LLM_BASE_URL", "https://embedding.test/v1")
    monkeypatch.setenv("EMBEDDER_API_KEY", "test-key")
    first, second = [1] * 1024, [2] * 1024

    def respond(request):
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(200, json={"data": [
            {"index": second_index, "embedding": second},
            {"index": 0, "embedding": first},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await embed_texts(["Первый", "Второй"], client=client)

    if second_index == 0:
        with pytest.raises(EmbeddingError, match="Invalid embedding provider response"):
            asyncio.run(run())
    else:
        assert asyncio.run(run()) == [first, second]
