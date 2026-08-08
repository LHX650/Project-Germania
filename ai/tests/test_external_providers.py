"""Provider-neutral external automotive intelligence contract tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import (
    CompositeExternalIntelligenceProvider,
    ExternalQuery,
    IntelligenceProviderError,
)


def test_external_evidence_model_contains_required_attribution() -> None:
    evidence = _evidence()

    assert evidence.source == "Official Association"
    assert evidence.category == "industry_report"
    assert evidence.brand is None
    assert evidence.vehicle is None
    assert evidence.reliability == 90
    assert evidence.fetched_time == "2026-08-08T00:00:00+00:00"
    assert evidence.evidence_type == "official_industry_report"
    assert evidence.region == "EU"


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"url": "http://example.org/report"}, "HTTPS"),
        ({"published_date": "not-a-date"}, "ISO-8601"),
        ({"reliability": 101}, "between 0 and 100"),
        ({"title": ""}, "cannot be empty"),
    ),
)
def test_external_evidence_rejects_invalid_metadata(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "source": "Official Association",
        "title": "Market report",
        "url": "https://example.org/report",
        "published_date": "2026-08-07",
        "category": "industry_report",
        "brand": None,
        "vehicle": None,
        "content_summary": "Attributed short summary.",
        "reliability": 90,
        "fetched_time": "2026-08-08T00:00:00+00:00",
        "evidence_type": "official_industry_report",
        "region": "EU",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        ExternalEvidence(**values)  # type: ignore[arg-type]


def test_composite_provider_deduplicates_urls_and_isolates_one_failure() -> None:
    provider = CompositeExternalIntelligenceProvider(
        (_MockProvider("news", (_evidence(),)), _FailingProvider())
    )

    results = provider.search(ExternalQuery(query="market", limit=5))

    assert results == (_evidence(),)
    assert provider.capabilities == frozenset({"news", "industry_report"})


def test_composite_provider_reports_failure_when_every_provider_fails() -> None:
    provider = CompositeExternalIntelligenceProvider((_FailingProvider(),))

    with pytest.raises(IntelligenceProviderError, match="unavailable"):
        provider.search(ExternalQuery(query="market"))


def _evidence() -> ExternalEvidence:
    return ExternalEvidence(
        source="Official Association",
        title="Market report",
        url="https://example.org/report",
        published_date="2026-08-07",
        category="industry_report",
        brand=None,
        vehicle=None,
        content_summary="Attributed short summary.",
        reliability=90,
        fetched_time="2026-08-08T00:00:00+00:00",
        evidence_type="official_industry_report",
        region="EU",
    )


@dataclass(frozen=True)
class _MockProvider:
    name: str
    evidence: tuple[ExternalEvidence, ...]
    capabilities: frozenset[str] = frozenset({"news"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        return self.evidence


@dataclass(frozen=True)
class _FailingProvider:
    name: str = "unavailable"
    capabilities: frozenset[str] = frozenset({"industry_report"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        raise IntelligenceProviderError("unavailable")
