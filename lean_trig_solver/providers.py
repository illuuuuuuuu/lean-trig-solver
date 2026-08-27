from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Raised when a model provider cannot return usable text."""


class ProofProvider(Protocol):
    def generate(self, system: str, user: str) -> str: ...


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    retries: int = 2,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code not in {408, 409, 429, 500, 502, 503, 504} or attempt == retries:
                raise ProviderError(f"Provider HTTP {error.code}: {detail[:1000]}") from error
        except URLError as error:
            if attempt == retries:
                raise ProviderError(f"Provider connection failed: {error.reason}") from error
        time.sleep(2**attempt)
    raise ProviderError("Provider request failed")


@dataclass
class OpenAIProvider:
    model: str
    api_key: str
    timeout: float = 120.0
    max_output_tokens: int = 3000
    endpoint: str = "https://api.openai.com/v1/responses"

    def generate(self, system: str, user: str) -> str:
        data = _post_json(
            self.endpoint,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": self.model,
                "instructions": system,
                "input": user,
                "max_output_tokens": self.max_output_tokens,
                "store": False,
            },
            self.timeout,
        )
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        chunks: list[str] = []
        for item in data.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        if not chunks:
            raise ProviderError("OpenAI response contained no output text")
        return "\n".join(chunks)


@dataclass
class AnthropicProvider:
    model: str
    api_key: str
    timeout: float = 120.0
    max_tokens: int = 3000
    endpoint: str = "https://api.anthropic.com/v1/messages"

    def generate(self, system: str, user: str) -> str:
        data = _post_json(
            self.endpoint,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            self.timeout,
        )
        chunks = [
            item["text"]
            for item in data.get("content", [])
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ]
        if not chunks:
            raise ProviderError("Anthropic response contained no output text")
        return "\n".join(chunks)


def build_provider(name: str, model: str | None = None) -> ProofProvider | None:
    normalized = name.lower()
    if normalized == "none":
        return None
    selected_model = model or os.environ.get("TRIG_SOLVER_MODEL")
    if not selected_model:
        raise ProviderError("Set --model or TRIG_SOLVER_MODEL")
    if normalized == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        return OpenAIProvider(model=selected_model, api_key=api_key)
    if normalized == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(model=selected_model, api_key=api_key)
    raise ProviderError(f"Unknown provider: {name}")

