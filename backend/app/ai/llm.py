"""LLM access layer.

``LLM_BACKEND=template`` (default) means no external model is called: the
reasoning module produces deterministic, fully offline explanations. Setting
``LLM_BACKEND=openai`` routes prompts to an OpenAI-compatible chat endpoint and
falls back to the template narrative if the call fails.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

import httpx

from app.core.config import LLMBackend, settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient(ABC):
    backend: str = "template"
    model: str = "n/a"

    @abstractmethod
    def complete(self, *, system: str, prompt: str, max_tokens: int | None = None, temperature: float | None = None) -> str | None:
        """Return generated text, or None when generation is unavailable."""

    def available(self) -> bool:
        return True


class NullLLM(LLMClient):
    """No-op client: signals callers to use deterministic templates."""

    backend = "template"
    model = "deterministic-template"

    def complete(self, *, system: str, prompt: str, max_tokens: int | None = None, temperature: float | None = None) -> str | None:
        return None

    def available(self) -> bool:
        return False


class OpenAIChatLLM(LLMClient):
    backend = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_BACKEND=openai")
        self.model = settings.llm_model
        self._base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    def complete(self, *, system: str, prompt: str, max_tokens: int | None = None, temperature: float | None = None) -> str | None:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
        }
        try:
            response = self._client.post(f"{self._base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return (content or "").strip() or None
        except Exception as exc:
            logger.warning("LLM completion failed (%s): %s", exc.__class__.__name__, exc)
            return None


_client: LLMClient | None = None
_lock = threading.Lock()


def get_llm() -> LLMClient:
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        if settings.llm_backend is LLMBackend.openai:
            try:
                _client = OpenAIChatLLM()
                logger.info("LLM backend: openai (%s)", _client.model)
            except Exception as exc:
                logger.warning("OpenAI backend unavailable (%s); using template reasoning", exc)
                _client = NullLLM()
        else:
            _client = NullLLM()
    return _client


def reset_llm() -> None:
    global _client
    with _lock:
        _client = None
