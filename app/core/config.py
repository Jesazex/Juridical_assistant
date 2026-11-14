"""DeepSeek settings, independent of the existing embedding provider settings."""

import os
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class DeepSeekConfigurationError(ValueError):
    """DeepSeek settings are present but invalid; messages never include values."""


@dataclass(frozen=True)
class DeepSeekSettings:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""
    timeout: float = 60.0

    @property
    def missing_parameters(self) -> tuple[str, ...]:
        return tuple(name for name, value in (
            ("DEEPSEEK_BASE_URL", self.base_url),
            ("DEEPSEEK_API_KEY", self.api_key),
            ("DEEPSEEK_MODEL", self.model),
        ) if not value)

    @property
    def is_configured(self) -> bool:
        return not self.missing_parameters


def get_deepseek_settings() -> DeepSeekSettings:
    # Do not export .env into os.environ or reuse LLM_* (reserved for BGE-M3).
    values = dotenv_values(ENV_FILE, interpolate=False) | os.environ
    base_url = (values.get("DEEPSEEK_BASE_URL") or "").strip()
    api_key = (values.get("DEEPSEEK_API_KEY") or "").strip()
    model = (values.get("DEEPSEEK_MODEL") or "").strip()
    settings = DeepSeekSettings(base_url=base_url, api_key=api_key, model=model)
    # Missing required parameters disable generation, including validation of unused options.
    if not settings.is_configured:
        return settings
    timeout_value = (values.get("DEEPSEEK_TIMEOUT") or "").strip() or "60"
    try:
        timeout = float(timeout_value)
    except ValueError:
        raise DeepSeekConfigurationError("DEEPSEEK_TIMEOUT must be a positive finite number") from None
    if not isfinite(timeout) or timeout <= 0:
        raise DeepSeekConfigurationError("DEEPSEEK_TIMEOUT must be a positive finite number")

    if base_url:
        try:
            url = urlsplit(base_url)
            valid = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and url.port != 0
                and url.username is None
                and url.password is None
                and not url.query
                and not url.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise DeepSeekConfigurationError(
                "DEEPSEEK_BASE_URL must be an HTTP(S) URL without credentials, query or fragment"
            ) from None

    if api_key and (not api_key.isascii() or any(char.isspace() for char in api_key)):
        raise DeepSeekConfigurationError("DEEPSEEK_API_KEY must be a single ASCII token")
    return DeepSeekSettings(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
