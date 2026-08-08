from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from ai.intelligence.api_providers import (
    ClaudeProvider,
    GeminiProvider,
    OpenAIProvider,
)
from ai.intelligence.providers import AgentLLMRequest, IntelligenceProviderError


@pytest.mark.parametrize(
    ("provider", "response", "expected_url", "key_header"),
    (
        (
            "openai",
            {
                "output": [
                    {"content": [{"type": "output_text", "text": "grounded answer"}]}
                ]
            },
            "https://api.openai.com/v1/responses",
            "Authorization",
        ),
        (
            "claude",
            {"content": [{"type": "text", "text": "grounded answer"}]},
            "https://api.anthropic.com/v1/messages",
            "x-api-key",
        ),
        (
            "gemini",
            {"candidates": [{"content": {"parts": [{"text": "grounded answer"}]}}]},
            "https://generativelanguage.googleapis.com/v1beta/models/",
            "x-goog-api-key",
        ),
    ),
)
def test_api_provider_uses_environment_key_and_returns_grounded_digest(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    response: dict[str, Any],
    expected_url: str,
    key_header: str,
) -> None:
    key_variable = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }[provider]
    monkeypatch.setenv(key_variable, "test-secret")
    transport = _FakeTransport(response)
    instance = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "gemini": GeminiProvider,
    }[provider](transport=transport)

    result = instance.generate(_request())

    assert result.markdown == "grounded answer"
    assert result.evidence_sha256 == "evidence-digest"
    assert transport.url.startswith(expected_url)
    assert key_header in transport.headers
    assert "test-secret" in transport.headers[key_header]
    assert "test-secret" not in str(transport.payload)
    assert transport.timeout == 30.0


@pytest.mark.parametrize(
    ("provider_class", "key_variable"),
    (
        (OpenAIProvider, "OPENAI_API_KEY"),
        (ClaudeProvider, "ANTHROPIC_API_KEY"),
        (GeminiProvider, "GOOGLE_API_KEY"),
    ),
)
def test_missing_api_key_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    provider_class: type[OpenAIProvider | ClaudeProvider | GeminiProvider],
    key_variable: str,
) -> None:
    monkeypatch.delenv(key_variable, raising=False)
    if key_variable == "GOOGLE_API_KEY":
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(IntelligenceProviderError, match="not configured"):
        provider_class(transport=_FakeTransport({})).generate(_request())


def test_provider_rejects_response_without_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    with pytest.raises(IntelligenceProviderError, match="no output text"):
        OpenAIProvider(transport=_FakeTransport({"output": []})).generate(_request())


def _request() -> AgentLLMRequest:
    return AgentLLMRequest(
        question="What changed?",
        intent="daily_brief",
        evidence_sha256="evidence-digest",
        evidence_json='{"metric":42}',
        grounded_draft_markdown="## Situation Summary\n\nGrounded",
        system_prompt="Use only evidence.",
    )


@dataclass
class _FakeTransport:
    response: dict[str, Any]
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    payload: dict[str, object] = field(default_factory=dict)
    timeout: float = 0

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> dict[str, Any]:
        self.url = url
        self.headers = headers
        self.payload = payload
        self.timeout = timeout
        return self.response
