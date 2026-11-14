"""Non-streaming DeepSeek Chat Completions client; the caller owns HTTP resources."""

from collections.abc import Sequence
from typing import Literal, TypedDict

import httpx

from app.llm import deepseec_exseptions as exceptions


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class DeepSeekClient:
    def __init__(self, http_client: httpx.AsyncClient, model: str) -> None:
        self.http_client = http_client
        self.model = model

    async def generate(
        self, messages: Sequence[ChatMessage], *,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> str:
        """Generate once; retries and the HTTP client's lifetime belong to the caller.

        Optional sampling/token limits follow the Chat Completions contract:
        https://api-docs.deepseek.com/api/create-chat-completion/
        """
        exceptions.validate_generation_parameters(messages, temperature, max_tokens)
        body: dict[str, object] = {
            "model": self.model, "messages": list(messages), "stream": False,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        try:
            response = await self.http_client.post("chat/completions", json=body)
        except httpx.RequestError as error:
            exceptions.raise_transport_error(error)

        exceptions.validate_http_response(response)
        return exceptions.parse_generation_response(response)
