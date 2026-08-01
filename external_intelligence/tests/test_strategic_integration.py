from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.config import (
    ExternalIntelligenceConfig,
    HTTPConfig,
    KBAConfig,
    NewsSourceConfig,
)
from external_intelligence.http import HTTPResponse
from external_intelligence.kba import KBAOfficialProvider
from external_intelligence.news import OfficialBrandNewsProvider, RSSNewsProvider
from external_intelligence.service import ExternalProviderSuite
from strategic.pipeline import run_strategic_report_stage
from strategic.tests.test_pipeline import write_ai_report, write_analytics


@dataclass(frozen=True)
class MappingFetcher:
    responses: dict[str, bytes]

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        del headers
        return HTTPResponse(self.responses[url], 200, "application/rss+xml")


def test_strategic_stage_reads_external_sources_and_writes_unified_json(
    tmp_path: Path,
) -> None:
    market_feed = b"""<rss version="2.0"><channel><item>
<title>German market context for Dynamic Motors</title>
<link>https://news.example.test/market</link>
<pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate>
<description>Attributed market context.</description><category>market</category>
</item></channel></rss>"""
    brand_feed = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Dynamic Motors Alpha product update</title>
<link href="https://brand.example.test/alpha" />
<published>2026-07-29T09:00:00Z</published>
<summary>Official Alpha product update.</summary><category term="product" />
</entry></feed>"""
    market_source = NewsSourceConfig(
        source_id="market_fixture",
        source_name="Market fixture",
        page_url="https://news.example.test/",
        feed_url="https://news.example.test/feed.xml",
        country="DE",
        ttl_seconds=3600,
    )
    brand_source = NewsSourceConfig(
        source_id="brand_fixture",
        source_name="Dynamic official newsroom",
        page_url="https://brand.example.test/",
        feed_url="https://brand.example.test/feed.xml",
        country="DE",
        ttl_seconds=3600,
        brand="Dynamic Motors",
    )
    config = ExternalIntelligenceConfig(
        cache_directory=tmp_path / "cache",
        output_path=tmp_path / "external.json",
        http=HTTPConfig(10, 1_000_000, "fixture"),
        kba=KBAConfig(
            False,
            "KBA fixture",
            "https://www.kba.de/monthly",
            "https://www.kba.de/fz10_{year}_{month:02d}.xlsx",
            1,
            3600,
        ),
        news_sources=(market_source,),
        brand_news_sources=(brand_source,),
        max_news_items_per_source=10,
    )
    fetcher = MappingFetcher(
        {
            market_source.feed_url or "": market_feed,
            brand_source.feed_url or "": brand_feed,
        }
    )
    cache = ExternalIntelligenceCache(config.cache_directory)
    suite = ExternalProviderSuite(
        config=config,
        kba=KBAOfficialProvider(
            config=config.kba,
            cache=cache,
            fetcher=fetcher,
        ),
        news=RSSNewsProvider(
            sources=config.news_sources,
            cache=cache,
            fetcher=fetcher,
            max_items_per_source=10,
        ),
        brand_news=OfficialBrandNewsProvider(
            sources=config.brand_news_sources,
            cache=cache,
            fetcher=fetcher,
            max_items_per_source=10,
        ),
    )
    external_output = tmp_path / "external.json"
    strategic_output = tmp_path / "strategic.md"

    result = run_strategic_report_stage(
        analytics_input_path=write_analytics(tmp_path / "analytics.json"),
        ai_input_path=write_ai_report(tmp_path / "ai.md"),
        output_path=strategic_output,
        provider_suite=suite,
        external_output_path=external_output,
    )

    assert result.strategic_status == "completed"
    assert result.external_signal_count == 2
    payload = json.loads(external_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["news"]["articles"][0]["source"] == "Market fixture"
    brand_article = payload["brand_news"]["articles"][0]
    assert brand_article["brands"] == ["Dynamic Motors"]
    assert brand_article["models"] == ["Dynamic Motors Alpha"]
    assert brand_article["country"] == "DE"
    assert brand_article["tags"] == ["product"]
    markdown = strategic_output.read_text(encoding="utf-8")
    assert "German market context for Dynamic Motors" in markdown
    assert "Dynamic Motors Alpha product update" in markdown
