"""Tests for grounded local and optional-provider report generation."""

from __future__ import annotations

from dataclasses import dataclass

from ai.analyst import REQUIRED_SECTIONS, generate_ai_market_report
from ai.models import parse_analytics_input
from ai.providers import LLMProviderError, LLMRequest, LLMResult
from ai.tests.test_models import analytics_payload


@dataclass(frozen=True)
class UnavailableProvider:
    """Provider fixture that represents an unavailable external API."""

    name: str = "unavailable-test-provider"

    def generate(self, request: LLMRequest) -> LLMResult:
        del request
        raise LLMProviderError("service unavailable")


@dataclass(frozen=True)
class EchoProvider:
    """Grounded provider fixture that returns the supplied local draft."""

    name: str = "echo-test-provider"

    def generate(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            markdown=request.grounded_draft_markdown,
            evidence_sha256=request.evidence_sha256,
        )


@dataclass(frozen=True)
class UngroundedProvider:
    """Provider fixture that inserts a number absent from the evidence."""

    name: str = "ungrounded-test-provider"

    def generate(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            markdown=f"{request.grounded_draft_markdown}\nUnsupported: 999.",
            evidence_sha256=request.evidence_sha256,
        )


def test_local_report_contains_required_grounded_analysis() -> None:
    report = parse_analytics_input(analytics_payload())

    generated = generate_ai_market_report(report)

    assert generated.generation_mode == "local_rules"
    assert all(section in generated.markdown for section in REQUIRED_SECTIONS)
    assert "Example Model One" in generated.markdown
    assert "73.50/100" in generated.markdown
    assert "EUR 42,000" in generated.markdown
    assert "transaction prices" in generated.markdown


def test_empty_data_generates_explicit_no_inference_report() -> None:
    report = parse_analytics_input(
        {"date": "2026-07-31", "vehicles": [], "brands": [], "methodology": {}}
    )

    generated = generate_ai_market_report(report)

    assert generated.generation_mode == "local_rules"
    assert "no vehicle or brand observations" in generated.markdown
    assert "No data-supported opportunity" in generated.markdown
    assert all(section in generated.markdown for section in REQUIRED_SECTIONS)


def test_unavailable_provider_falls_back_to_local_rules() -> None:
    report = parse_analytics_input(analytics_payload())

    generated = generate_ai_market_report(report, provider=UnavailableProvider())

    assert generated.generation_mode == "local_rules_fallback"
    assert generated.provider_name == "unavailable-test-provider"
    assert "service unavailable" in (generated.fallback_reason or "")
    assert "Example Model One" in generated.markdown


def test_grounded_provider_result_is_accepted() -> None:
    report = parse_analytics_input(analytics_payload())

    generated = generate_ai_market_report(report, provider=EchoProvider())

    assert generated.generation_mode == "llm_grounded"
    assert generated.provider_name == "echo-test-provider"


def test_ungrounded_provider_result_falls_back() -> None:
    report = parse_analytics_input(analytics_payload())

    generated = generate_ai_market_report(report, provider=UngroundedProvider())

    assert generated.generation_mode == "local_rules_fallback"
    assert "numbers absent from Analytics evidence" in (generated.fallback_reason or "")
    assert "Unsupported: 999" not in generated.markdown
