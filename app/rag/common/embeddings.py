"""BGE-M3 dense embeddings through the organizer's OpenAI-compatible API."""

import asyncio
import math
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
from dotenv import dotenv_values

EMBEDDING_DIMENSIONS = 1024
DEFAULT_MODEL = "BAAI/bge-m3"


class EmbeddingError(RuntimeError):
    """The provider could not return a usable embedding."""


def validate_embedding(vector: Sequence[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding components")
    if any(
        type(value) not in (float, int)
        or abs(value) > 3.4028234663852886e38
        or not math.isfinite(value)
        for value in vector
    ):
        raise ValueError("Embedding components must be finite float32 values")
    result = [float(value) for value in vector]
    if not any(abs(value) > 2**-150 for value in result):
        raise ValueError("Embedding must have nonzero norm")
    return result


def _parse_response(payload: dict, count: int) -> list[list[float]]:
    rows = payload["data"]
    by_index: dict[int, list[float]] = {}
    for row in rows:
        index = row["index"]
        if type(index) is not int or not 0 <= index < count or index in by_index:
            raise ValueError("Invalid embedding index")
        by_index[index] = validate_embedding(row["embedding"])
    if len(by_index) != count:
        raise ValueError("Wrong number of embeddings")
    return [by_index[index] for index in range(count)]


async def _request_batch(
    client: httpx.AsyncClient, url: str, key: str, model: str, texts: list[str]
) -> list[list[float]]:
    for attempt in range(3):
        try:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": texts, "encoding_format": "float"},
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise EmbeddingError("Embedding provider is unreachable") from None
        else:
            if response.is_success:
                try:
                    return _parse_response(response.json(), len(texts))
                except (KeyError, TypeError, ValueError):
                    raise EmbeddingError("Invalid embedding provider response") from None
            if attempt == 2 or not (response.status_code == 429 or response.status_code >= 500):
                raise EmbeddingError(f"Embedding provider returned HTTP {response.status_code}")
        await asyncio.sleep(0.5 * 2**attempt)
    raise AssertionError("Embedding retries exhausted")


async def embed_texts(
    texts: Sequence[str], *, client: httpx.AsyncClient | None = None
) -> list[list[float]]:
    if isinstance(texts, str) or not texts or any(not text.strip() for text in texts):
        raise ValueError("Provide a sequence of nonblank texts")

    env_file = Path(__file__).resolve().parents[3] / ".env"
    config = dotenv_values(env_file, interpolate=False) | os.environ
    base_url = config.get("LLM_BASE_URL") or config.get("OPENAI_BASE_URL")
    key = (
        config.get("EMBEDDER_API_KEY")
        or config.get("LLM_API_KEY")
        or config.get("OPENAI_API_KEY")
    )
    if not base_url or not key:
        raise EmbeddingError("Configure the embedding provider URL and API key")

    async def fetch(active_client: httpx.AsyncClient) -> list[list[float]]:
        vectors: list[list[float]] = []
        model = config.get("EMB_MODEL") or DEFAULT_MODEL
        for start in range(0, len(texts), 16):
            vectors.extend(await _request_batch(
                active_client, base_url.rstrip("/") + "/embeddings", key,
                model, list(texts[start:start + 16]),
            ))
        return vectors

    if client is not None:
        return await fetch(client)
    async with httpx.AsyncClient(timeout=60.0) as active_client:
        return await fetch(active_client)
