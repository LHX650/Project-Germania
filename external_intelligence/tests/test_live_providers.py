"""Offline tests for Phase 18B live external providers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from ai.intelligence.providers import ExternalQuery
from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.http import HTTPResponse
from external_intelligence.live_config import (
    LiveExternalConfig,
    LiveHTTPConfig,
    LiveSourceConfig,
    load_live_config,
)
from external_intelligence.live_providers import (
    AutomotiveNewsLiveProvider,
    OfficialBrandNewsLiveProvider,
    PolicyRegulationLiveProvider,
    build_live_providers_from_config,
    collect_live_external_intelligence,
)

NOW = datetime(2026, 8, 8, 12, tzinfo=UTC)


def test_live_rss_provider_filters_30_days_and_deduplicates_urls(
    tmp_path: Path,
) -> None:
    source = _source("automotive_news", "https://example.org/news.xml")
    fetcher = _Fetcher(
        {
            source.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Duplicate automotive update",
                            "https://example.org/recent",
                            "Thu, 06 Aug 2026 08:00:00 GMT",
                        ),
                        (
                            "Recent automotive update",
                            "https://example.org/recent",
                            "Fri, 07 Aug 2026 08:00:00 GMT",
                        ),
                        (
                            "Old automotive update",
                            "https://example.org/old",
                            "Mon, 01 Jun 2026 08:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            )
        }
    )
    provider = AutomotiveNewsLiveProvider(
        provider_kind="automotive_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert result.status == "available"
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.title == "Recent automotive update"
    assert evidence.reliability == 90
    assert datetime.fromisoformat(evidence.fetched_time).date() == NOW.date()
    assert evidence.evidence_type == "official_industry_news"
    assert evidence.region == "EU"


def test_missing_rss_image_uses_official_page_open_graph_metadata(
    tmp_path: Path,
) -> None:
    source = _source("automotive_news", "https://example.org/news.xml")
    article_url = "https://example.org/recent"
    fetcher = _Fetcher(
        {
            source.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Recent automotive update",
                            article_url,
                            "Fri, 07 Aug 2026 08:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            ),
            article_url: HTTPResponse(
                body=b'<meta property="og:image" content="/images/update.jpg">',
                status_code=200,
                content_type="text/html",
            ),
        }
    )
    provider = AutomotiveNewsLiveProvider(
        provider_kind="automotive_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    evidence = provider.fetch(ExternalQuery(query="")).evidence[0]

    assert evidence.image_url == "https://example.org/images/update.jpg"
    assert evidence.image_source == "og:image"


def test_image_metadata_timeout_isolated_from_article_provider(
    tmp_path: Path,
) -> None:
    source = _source("automotive_news", "https://example.org/news.xml")
    article_url = "https://example.org/recent"
    fetcher = _Fetcher(
        {
            source.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Recent automotive update",
                            article_url,
                            "Fri, 07 Aug 2026 08:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            ),
            article_url: TimeoutError("image metadata timeout"),
        }
    )
    provider = AutomotiveNewsLiveProvider(
        provider_kind="automotive_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert result.status == "available"
    assert len(result.evidence) == 1
    assert result.evidence[0].image_url is None
    assert result.failed_sources == ()


def test_provider_failure_is_isolated_when_another_source_succeeds(
    tmp_path: Path,
) -> None:
    good = _source("policy_regulation", "https://example.org/good.xml")
    failed = _source(
        "policy_regulation",
        "https://example.org/failed.xml",
        source_id="failed",
        source_name="Failed authority",
    )
    fetcher = _Fetcher(
        {
            good.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Official vehicle regulation update",
                            "https://example.org/regulation",
                            "Fri, 07 Aug 2026 08:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            ),
            failed.feed_url: OSError("network unavailable"),
        }
    )
    provider = PolicyRegulationLiveProvider(
        provider_kind="policy_regulation",
        sources=(good, failed),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert result.status == "partial"
    assert len(result.evidence) == 1
    assert result.failed_sources == ("Failed authority",)
    assert any("network unavailable" in item for item in result.errors)


def test_empty_recent_window_returns_insufficient_data(tmp_path: Path) -> None:
    source = _source("automotive_news", "https://example.org/old.xml")
    fetcher = _Fetcher(
        {
            source.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Historical item",
                            "https://example.org/historical",
                            "Mon, 01 Jun 2026 08:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            )
        }
    )
    provider = AutomotiveNewsLiveProvider(
        provider_kind="automotive_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert result.status == "insufficient_data"
    assert result.evidence == ()
    assert result.insufficient_sources == ("Official source",)


def test_policy_provider_rejects_unrelated_general_transport_item(
    tmp_path: Path,
) -> None:
    source = _source("policy_regulation", "https://example.org/policy.xml")
    fetcher = _Fetcher(
        {
            source.feed_url: HTTPResponse(
                body=_rss(
                    (
                        (
                            "Tourism corridor cooperation update",
                            "https://example.org/tourism",
                            "Fri, 07 Aug 2026 08:00:00 GMT",
                        ),
                        (
                            "Electric vehicle charging regulation update",
                            "https://example.org/vehicle-policy",
                            "Fri, 07 Aug 2026 09:00:00 GMT",
                        ),
                    )
                ),
                status_code=200,
                content_type="application/rss+xml",
            )
        }
    )
    provider = PolicyRegulationLiveProvider(
        provider_kind="policy_regulation",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert [item.title for item in result.evidence] == [
        "Electric vehicle charging regulation update"
    ]


def test_generic_api_transport_maps_to_external_evidence(tmp_path: Path) -> None:
    source = _source(
        "policy_regulation",
        None,
        transport="api",
        page_url="https://example.org/policy-api",
    )
    response = HTTPResponse(
        body=json.dumps(
            {
                "items": [
                    {
                        "title": "API electric vehicle policy update",
                        "url": "https://example.org/policy/1",
                        "published_date": "2026-08-07T09:00:00+00:00",
                        "summary": "Official public API metadata.",
                    }
                ]
            }
        ).encode(),
        status_code=200,
        content_type="application/json",
    )
    fetcher = _Fetcher({source.page_url: response})
    provider = PolicyRegulationLiveProvider(
        provider_kind="policy_regulation",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=fetcher,
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    result = provider.fetch(ExternalQuery(query=""))

    assert result.evidence[0].title == "API electric vehicle policy update"
    assert result.evidence[0].category == "policy_regulation"


def test_vda_style_api_path_and_text_are_mapped(tmp_path: Path) -> None:
    source = _source(
        "automotive_news",
        None,
        transport="api",
        page_url="https://www.vda.de/.rest/pressreleases/v1",
    )
    response = HTTPResponse(
        body=json.dumps(
            {
                "items": [
                    {
                        "path": "/en/press/press-releases/2026/market-july",
                        "title": "Production and Market in July 2026",
                        "text": "Electric vehicle registrations update.",
                        "date": "2026-08-06T00:00:00+02:00",
                    }
                ]
            }
        ).encode(),
        status_code=200,
        content_type="application/json",
    )
    provider = AutomotiveNewsLiveProvider(
        provider_kind="automotive_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=_Fetcher({source.page_url: response}),
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    evidence = provider.fetch(ExternalQuery(query="")).evidence[0]

    assert evidence.url == (
        "https://www.vda.de/en/press/press-releases/2026/market-july"
    )
    assert evidence.content_summary == "Electric vehicle registrations update."


def test_mercedes_official_api_builds_detail_url_and_model_evidence(
    tmp_path: Path,
) -> None:
    source = replace(
        _source(
            "official_brand_news",
            None,
            transport="api",
            page_url="https://api.media.mercedes-benz.com/en/jsonapi/search/full",
        ),
        source_id="mercedes_official_news",
        source_name="Mercedes-Benz Media",
        brand="Mercedes-Benz",
    )
    response = HTTPResponse(
        body=json.dumps(
            {
                "results": [
                    {
                        "id": "9f9ddd25-7474-476e-b16f-28961098f429",
                        "title": "The all-new electric C-Class",
                        "fuel_label": "Official C-Class product information.",
                        "display_date": "2026-07-28T08:00:00Z",
                        "header_image_uuid": "image-uuid",
                    }
                ]
            }
        ).encode(),
        status_code=200,
        content_type="application/json",
    )
    provider = OfficialBrandNewsLiveProvider(
        provider_kind="official_brand_news",
        sources=(source,),
        cache=ExternalIntelligenceCache(tmp_path),
        fetcher=_Fetcher({source.page_url: response}),
        recent_days=30,
        max_items=10,
        clock=lambda: NOW,
    )

    evidence = provider.fetch(
        ExternalQuery(
            query="",
            brands=("Mercedes-Benz",),
            vehicles=("Mercedes-Benz C-Class", "Mercedes-Benz GLC"),
        )
    ).evidence[0]

    assert evidence.vehicle == "Mercedes-Benz C-Class"
    assert evidence.url.endswith("/9f9ddd25-7474-476e-b16f-28961098f429")
    assert evidence.image_source == "provider_metadata"


def test_config_builds_four_provider_categories_and_collection_dedupes(
    tmp_path: Path,
) -> None:
    config = LiveExternalConfig(
        cache_directory=tmp_path,
        recent_days=30,
        max_items_per_provider=5,
        http=LiveHTTPConfig(5, 100_000, "test-agent"),
        sources=tuple(
            _source(kind, f"https://example.org/{kind}.xml")
            for kind in (
                "automotive_news",
                "policy_regulation",
                "official_brand_news",
                "industry_report",
            )
        ),
    )
    response = HTTPResponse(
        body=_rss(
            (
                (
                    "Shared automotive vehicle update",
                    "https://example.org/shared",
                    "Fri, 07 Aug 2026 08:00:00 GMT",
                ),
            )
        ),
        status_code=200,
        content_type="application/rss+xml",
    )
    fetcher = _Fetcher(
        {source.feed_url: response for source in config.sources if source.feed_url}
    )
    providers = build_live_providers_from_config(
        config,
        fetcher=fetcher,
        clock=lambda: NOW,
    )

    collection = collect_live_external_intelligence(
        providers,
        ExternalQuery(query=""),
        fetched_at=NOW,
    )

    assert {provider.provider_kind for provider in providers} == {
        "automotive_news",
        "policy_regulation",
        "official_brand_news",
        "industry_report",
    }
    assert len(collection.evidence) == 1
    assert all(result.status == "available" for result in collection.providers)


def test_repository_live_config_is_valid() -> None:
    config = load_live_config()

    assert config.recent_days == 30
    assert {source.provider_kind for source in config.sources} == {
        "automotive_news",
        "policy_regulation",
        "official_brand_news",
        "industry_report",
    }
    official_brands = {
        source.brand
        for source in config.sources
        if source.provider_kind == "official_brand_news"
    }
    assert official_brands == {
        "Audi",
        "BMW",
        "BYD",
        "MG",
        "Mercedes-Benz",
        "NIO",
        "Tesla",
        "Volkswagen",
        "XPENG",
        "Škoda",
    }
    assert {
        source.source_name
        for source in config.sources
        if source.provider_kind == "policy_regulation"
    } == {
        "European Commission Directorate-General for Mobility and Transport",
        "German Federal Ministry for Transport (BMV)",
    }


def _source(
    provider_kind: str,
    feed_url: str | None,
    *,
    source_id: str = "source",
    source_name: str = "Official source",
    transport: str = "rss_or_html",
    page_url: str = "https://example.org/page",
) -> LiveSourceConfig:
    is_brand = provider_kind == "official_brand_news"
    return LiveSourceConfig(
        source_id=f"{source_id}-{provider_kind}",
        source_name=source_name,
        provider_kind=provider_kind,  # type: ignore[arg-type]
        page_url=page_url,
        feed_url=feed_url,
        transport=transport,
        region="EU",
        category={
            "automotive_news": "automotive_news",
            "policy_regulation": "policy_regulation",
            "official_brand_news": "brand_intelligence",
            "industry_report": "industry_report",
        }[provider_kind],
        evidence_type={
            "automotive_news": "official_industry_news",
            "policy_regulation": "official_policy_update",
            "official_brand_news": "official_brand_release",
            "industry_report": "official_industry_report",
        }[provider_kind],
        reliability=95 if is_brand else 90,
        ttl_seconds=3600,
        brand="BMW" if is_brand else None,
    )


def _rss(items: tuple[tuple[str, str, str], ...]) -> bytes:
    entries = "".join(
        f"<item><title>{title}</title><link>{url}</link>"
        f"<pubDate>{published}</pubDate>"
        f"<description>{title} summary</description></item>"
        for title, url, published in items
    )
    return f"<rss><channel>{entries}</channel></rss>".encode()


@dataclass
class _Fetcher:
    responses: dict[str | None, HTTPResponse | Exception]

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        del headers
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response
