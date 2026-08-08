"""Dashboard adapter tests for unified external automotive evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from services.content_feed import ContentFeed, ContentRecord
from services.external_intelligence import (
    ContentFeedExternalIntelligenceProvider,
    build_default_external_provider,
    build_hub_intelligence_sections,
    build_live_hub_sections,
    live_external_enabled,
)
from services.runtime import get_dashboard_data_paths

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import ExternalQuery


def test_content_feed_adapter_returns_unified_external_evidence() -> None:
    feed = _feed((_record(),))
    provider = ContentFeedExternalIntelligenceProvider(loader=lambda: feed)

    results = provider.search(
        ExternalQuery(query="BMW market", brands=("BMW",), limit=3)
    )

    assert len(results) == 1
    evidence = results[0]
    assert evidence.source == "Official source"
    assert evidence.url == "https://example.org/news"
    assert evidence.published_date == "2026-08-07T00:00:00+00:00"
    assert evidence.category == "news"
    assert evidence.brand == "BMW"
    assert evidence.vehicle == "BMW iX1"
    assert evidence.content_summary == "Attributed short summary."
    assert evidence.reliability == 85
    assert evidence.fetched_time == "2026-08-08T00:00:00+00:00"
    assert evidence.evidence_type == "validated_content_feed_news"
    assert evidence.region == "DE"


def test_empty_content_feed_returns_no_external_evidence() -> None:
    provider = ContentFeedExternalIntelligenceProvider(loader=lambda: _feed(()))

    assert provider.search(ExternalQuery(query="market")) == ()


def test_hub_sections_use_only_current_content_metadata() -> None:
    brand_news = _record()
    broad_news = _record(
        content_id="broad-news",
        title="European market context",
        source_url="https://example.org/market",
        brands=(),
        vehicles=(),
    )
    report = _record(
        content_id="report",
        content_type="report",
        title="Industry report",
        source_url="https://example.org/report-page",
        document_url="https://example.org/report.pdf",
        brands=(),
        vehicles=(),
    )

    sections = build_hub_intelligence_sections((brand_news, broad_news, report))

    assert sections.external_news == (brand_news, broad_news)
    assert sections.brand_updates == (brand_news,)
    assert sections.industry_signals == (broad_news, report)


def test_live_hub_sections_keep_four_external_signal_types_distinct() -> None:
    evidence = (
        _external("automotive_news"),
        _external("policy_regulation"),
        _external("brand_intelligence"),
        _external("industry_report"),
    )

    sections = build_live_hub_sections((), evidence)

    assert sections.latest_automotive_news == (evidence[0],)
    assert sections.policy_updates == (evidence[1],)
    assert sections.brand_intelligence == (evidence[2],)
    assert sections.industry_signals == (evidence[3],)


def test_demo_mode_uses_public_content_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")

    results = ContentFeedExternalIntelligenceProvider().search(
        ExternalQuery(query="", limit=10)
    )

    assert results
    assert all(item.url.startswith("https://") for item in results)
    assert live_external_enabled() is False


def test_production_mode_combines_mock_live_provider_without_real_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LIVE_EXTERNAL_INTELLIGENCE", "true")
    provider = build_default_external_provider(live_providers=(_MockLiveProvider(),))

    results = provider.search(ExternalQuery(query="", limit=100))

    assert live_external_enabled() is True
    assert any(item.url == "https://example.org/live-policy" for item in results)


def test_production_mode_reads_current_artifact_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    if not get_dashboard_data_paths().content_feed.is_file():
        pytest.skip("production content feed is not present")

    results = ContentFeedExternalIntelligenceProvider().search(
        ExternalQuery(query="", limit=10)
    )

    assert all(item.url.startswith("https://") for item in results)


def _feed(items: tuple[ContentRecord, ...]) -> ContentFeed:
    return ContentFeed(
        report_date=date(2026, 8, 8),
        generated_at=datetime(2026, 8, 8, tzinfo=UTC),
        counts={
            kind: sum(item.content_type == kind for item in items)
            for kind in ("news", "report", "video")
        },
        items=items,
        sources=(),
        source_path=Path("content_feed.json"),
    )


def _record(**overrides: object) -> ContentRecord:
    values: dict[str, object] = {
        "content_id": "brand-news",
        "content_type": "news",
        "title": "Verified BMW update",
        "source_name": "Official source",
        "source_url": "https://example.org/news",
        "published_at": datetime(2026, 8, 7, tzinfo=UTC),
        "summary": "Attributed short summary.",
        "language": "en",
        "region": "DE",
        "brands": ("BMW",),
        "vehicles": ("BMW iX1",),
        "topics": ("market",),
        "impact_level": "medium",
        "thumbnail_url": None,
        "document_url": None,
        "video_id": None,
        "collected_at": datetime(2026, 8, 8, tzinfo=UTC),
        "evidence_status": "verified_source",
        "ai_summary": "Local summary.",
        "summary_mode": "local_rules",
    }
    values.update(overrides)
    return ContentRecord(**values)  # type: ignore[arg-type]


def _external(category: str) -> ExternalEvidence:
    return ExternalEvidence(
        source="Official source",
        title=f"{category} evidence",
        url=f"https://example.org/{category}",
        published_date="2026-08-07T00:00:00+00:00",
        category=category,
        brand="BMW" if category == "brand_intelligence" else None,
        vehicle=None,
        content_summary="Attributed external metadata.",
        reliability=95,
        fetched_time="2026-08-08T00:00:00+00:00",
        evidence_type=category,
        region="EU",
    )


class _MockLiveProvider:
    name = "mock_live_policy"
    capabilities = frozenset({"policy_regulation"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        return (
            ExternalEvidence(
                source="European Commission",
                title="Live policy update",
                url="https://example.org/live-policy",
                published_date="2026-08-07T00:00:00+00:00",
                category="policy_regulation",
                brand=None,
                vehicle=None,
                content_summary="Official policy metadata.",
                reliability=100,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="official_policy_update",
                region="EU",
            ),
        )
