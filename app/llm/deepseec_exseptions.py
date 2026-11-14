"""DeepSeek exceptions and validation helpers; no network requests are performed here."""

from collections.abc import Sequence
from typing import NoReturn

import httpx


class DeepSeekError(RuntimeError):
    """A generation failed. Error messages never contain provider bodies or credentials."""


class DeepSeekHTTPError(DeepSeekError):
    """An unsuccessful HTTP response, with a safe status code for callers."""

    def __init__(self, status_code: int, message: str = "DeepSeek request failed") -> None:
        self.status_code = status_code
        super().__init__(f"{message} (HTTP {status_code})")


class DeepSeekAuthenticationError(DeepSeekHTTPError):
    """The provider rejected authorization (401/403)."""


class DeepSeekRateLimitError(DeepSeekHTTPError):
    """The provider rate limit was reached (429)."""


class DeepSeekServerError(DeepSeekHTTPError):
    """The provider returned a server error (5xx)."""


class DeepSeekTimeoutError(DeepSeekError):
    """The HTTP request exceeded its timeout."""


class DeepSeekNetworkError(DeepSeekError):
    """A network or transport error prevented the request from completing."""


class DeepSeekInvalidJSONError(DeepSeekError):
    """The provider did not return valid JSON."""


class DeepSeekInvalidResponseError(DeepSeekError):
    """The response does not match the Chat Completions text response structure."""


class DeepSeekEmptyResponseError(DeepSeekError):
    """The model returned no usable answer text."""


def validate_generation_parameters(
    messages: Sequence[object], temperature: float | None, max_tokens: int | None,
) -> None:
    """Reject invalid inputs before any HTTP request is sent."""
    if not messages:
        raise ValueError("At least one chat message is required")
    if temperature is not None:
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
    if max_tokens is not None:
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")


def raise_transport_error(error: httpx.RequestError) -> NoReturn:
    """Translate transport failures without exposing the original exception."""
    if isinstance(error, httpx.TimeoutException):
        raise DeepSeekTimeoutError("DeepSeek request timed out") from None
    raise DeepSeekNetworkError("DeepSeek provider is unreachable") from None


def validate_http_response(response: httpx.Response) -> None:
    """Check HTTP status without copying provider bodies or URLs into errors."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        status = response.status_code
        # Do not include the response body, URL or original HTTPX exception.
        if status in {401, 403}:
            raise DeepSeekAuthenticationError(status, "DeepSeek authorization failed") from None
        if status == 429:
            raise DeepSeekRateLimitError(status, "DeepSeek rate limit exceeded") from None
        if 500 <= status < 600:
            raise DeepSeekServerError(status, "DeepSeek server error") from None
        raise DeepSeekHTTPError(status) from None


def parse_generation_response(response: httpx.Response) -> str:
    """Parse JSON and require a nonempty first-choice answer, preserving formatting."""
    try:
        payload = response.json()
    except ValueError:
        raise DeepSeekInvalidJSONError("DeepSeek returned invalid JSON") from None

    if not isinstance(payload, dict):
        raise DeepSeekInvalidResponseError("DeepSeek response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise DeepSeekInvalidResponseError("DeepSeek response must contain a nonempty choices list")
    message = choices[0].get("message")
    if not isinstance(message, dict) or "content" not in message:
        raise DeepSeekInvalidResponseError("DeepSeek response is missing message.content")
    content = message["content"]
    if content is None:
        raise DeepSeekEmptyResponseError("DeepSeek returned an empty answer")
    if not isinstance(content, str):
        raise DeepSeekInvalidResponseError("DeepSeek message.content must be a string")
    if not content.strip():
        raise DeepSeekEmptyResponseError("DeepSeek returned an empty answer")
    return content
