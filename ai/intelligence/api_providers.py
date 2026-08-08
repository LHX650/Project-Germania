"""Environment-configured REST adapters for supported LLM providers."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ai.intelligence.providers import (
    AgentLLMRequest,
    AgentLLMResult,
    IntelligenceProviderError,
)

DEFAULT_TIMEOUT_SECONDS = 30.0


class JSONTransport(Protocol):
    """Small injectable JSON transport used by all REST adapters."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, Any]:
        """POST JSON and return a decoded object."""


class UrllibJSONTransport:
    """Dependency-free HTTPS JSON transport with bounded timeouts."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> dict[str, Any]:
        """POST a JSON request without logging credentials or response bodies."""

        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise IntelligenceProviderError(
                f"LLM provider returned HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise IntelligenceProviderError("LLM provider request failed.") from exc
        try:
            decoded = json.loads(body)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise IntelligenceProviderError(
                "LLM provider returned invalid JSON."
            ) from exc
        if not isinstance(decoded, dict):
            raise IntelligenceProviderError(
                "LLM provider response must be a JSON object."
            )
        return decoded


class OpenAIProvider:
    """Grounded OpenAI Responses API adapter."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: JSONTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._model = model or _environment_value("OPENAI_MODEL", "gpt-5-mini")
        self._timeout = _positive_timeout(timeout)
        self._transport = transport or UrllibJSONTransport()

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        """Generate a grounded answer through the Responses API."""

        api_key = _required_key(self._api_key, "OPENAI_API_KEY")
        payload = self._transport.post_json(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self._model,
                "instructions": request.system_prompt,
                "input": _user_prompt(request),
                "store": False,
            },
            timeout=self._timeout,
        )
        return AgentLLMResult(
            markdown=_openai_text(payload),
            evidence_sha256=request.evidence_sha256,
        )


class ClaudeProvider:
    """Grounded Anthropic Messages API adapter."""

    name = "claude"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: JSONTransport | None = None,
    ) -> None:
        self._api_key = (
            api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY")
        )
        self._model = model or _environment_value(
            "ANTHROPIC_MODEL", "claude-sonnet-4-5"
        )
        self._timeout = _positive_timeout(timeout)
        self._transport = transport or UrllibJSONTransport()

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        """Generate a grounded answer through the Messages API."""

        api_key = _required_key(self._api_key, "ANTHROPIC_API_KEY")
        payload = self._transport.post_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload={
                "model": self._model,
                "max_tokens": 2_048,
                "system": request.system_prompt,
                "messages": [{"role": "user", "content": _user_prompt(request)}],
            },
            timeout=self._timeout,
        )
        return AgentLLMResult(
            markdown=_claude_text(payload),
            evidence_sha256=request.evidence_sha256,
        )


class GeminiProvider:
    """Grounded Google Gemini generateContent REST adapter."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: JSONTransport | None = None,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        )
        self._model = model or _environment_value("GEMINI_MODEL", "gemini-3.5-flash")
        self._timeout = _positive_timeout(timeout)
        self._transport = transport or UrllibJSONTransport()

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        """Generate a grounded answer through generateContent."""

        api_key = _required_key(self._api_key, "GOOGLE_API_KEY")
        model = quote(self._model, safe="")
        payload = self._transport.post_json(
            (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            ),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            payload={
                "system_instruction": {"parts": [{"text": request.system_prompt}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": _user_prompt(request)}],
                    }
                ],
            },
            timeout=self._timeout,
        )
        return AgentLLMResult(
            markdown=_gemini_text(payload),
            evidence_sha256=request.evidence_sha256,
        )


def _user_prompt(request: AgentLLMRequest) -> str:
    return (
        "Answer the user question using only the supplied evidence. Preserve the "
        "six required Markdown headings and do not add unsupported numbers.\n\n"
        f"Question:\n{request.question}\n\n"
        f"Intent:\n{request.intent}\n\n"
        f"Evidence SHA-256:\n{request.evidence_sha256}\n\n"
        f"Evidence JSON:\n{request.evidence_json}\n\n"
        f"Grounded local draft:\n{request.grounded_draft_markdown}"
    )


def _openai_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for output in _objects(payload.get("output")):
        for content in _objects(output.get("content")):
            text = content.get("text")
            if (
                content.get("type") == "output_text"
                and isinstance(text, str)
                and text.strip()
            ):
                return text.strip()
    raise IntelligenceProviderError("OpenAI response contains no output text.")


def _claude_text(payload: Mapping[str, Any]) -> str:
    parts = [
        str(item["text"]).strip()
        for item in _objects(payload.get("content"))
        if item.get("type") == "text"
        and isinstance(item.get("text"), str)
        and str(item["text"]).strip()
    ]
    if not parts:
        raise IntelligenceProviderError("Claude response contains no text content.")
    return "\n".join(parts)


def _gemini_text(payload: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for candidate in _objects(payload.get("candidates")):
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in _objects(content.get("parts")):
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    if not parts:
        raise IntelligenceProviderError("Gemini response contains no text content.")
    return "\n".join(parts)


def _objects(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _required_key(value: str | None, variable: str) -> str:
    if value is None or not value.strip():
        raise IntelligenceProviderError(f"{variable} is not configured.")
    return value.strip()


def _positive_timeout(value: float) -> float:
    if value <= 0:
        raise ValueError("timeout must be positive")
    return float(value)


def _environment_value(variable: str, default: str) -> str:
    value = os.getenv(variable)
    return value.strip() if value is not None and value.strip() else default
