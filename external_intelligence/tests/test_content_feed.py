"""Tests for strict public content models, parsers, and feed generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from external_intelligence.content_feed import build_content_feed
from external_intelligence.content_models import (
    ContentItem,
    ContentType,
    ImpactLevel,
    parse_youtube_video_id,
)
from external_intelligence.content_parsing import (
    parse_page_image_metadata,
    parse_youtube_feed,
)
from external_intelligence.http import HTTPResponse


class FakeFetcher:
    def __init__(self, responses: dict[str, bytes] | None = None) -> None:
        self.responses = responses or {}

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        del headers
        if url not in self.responses:
            raise OSError("provider unavailable")
        content_type = (
            "application/atom+xml" if "youtube" in url else "application/json"
        )
        return HTTPResponse(self.responses[url], 200, content_type)


def test_news_report_video_models_and_youtube_id() -> None:
    collected = datetime(2026, 8, 1, 12, tzinfo=UTC)
    common = {
        "title": "Official item",
        "source_name": "Official source",
        "published_at": collected - timedelta(days=1),
        "summary": "Short attributed metadata.",
        "language": "en",
        "region": "EU",
        "brands": (),
        "vehicles": (),
        "topics": (),
        "impact_level": ImpactLevel.LOW,
        "thumbnail_url": None,
        "collected_at": collected,
        "evidence_status": "verified_source",
    }
    news = ContentItem(
        content_id="news-id",
        content_type=ContentType.NEWS,
        source_url="https://example.org/news",
        document_url=None,
        video_id=None,
        **common,
    )
    report = ContentItem(
        content_id="report-id",
        content_type=ContentType.REPORT,
        source_url="https://example.org/report",
        document_url="https://example.org/report.pdf",
        video_id=None,
        **common,
    )
    video = ContentItem(
        content_id="video-id",
        content_type=ContentType.VIDEO,
        source_url="https://www.youtube.com/watch?v=abcdefghijk",
        document_url=None,
        video_id="abcdefghijk",
        **common,
    )
    assert {news.content_type, report.content_type, video.content_type} == set(
        ContentType
    )
    assert parse_youtube_video_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert (
        parse_youtube_video_id("https://youtube.com/shorts/abcdefghijk")
        == "abcdefghijk"
    )


def test_model_rejects_invalid_url_and_future_time() -> None:
    collected = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="HTTPS"):
        ContentItem(
            content_id="bad",
            content_type=ContentType.NEWS,
            title="Bad URL",
            source_name="Source",
            source_url="javascript:alert(1)",
            published_at=collected,
            summary="Metadata",
            language="en",
            region="EU",
            brands=(),
            vehicles=(),
            topics=(),
            impact_level=ImpactLevel.LOW,
            thumbnail_url=None,
            document_url=None,
            video_id=None,
            collected_at=collected,
            evidence_status="verified_source",
        )
    with pytest.raises(ValueError, match="later"):
        ContentItem(
            content_id="future",
            content_type=ContentType.NEWS,
            title="Future",
            source_name="Source",
            source_url="https://example.org/future",
            published_at=collected + timedelta(seconds=1),
            summary="Metadata",
            language="en",
            region="EU",
            brands=(),
            vehicles=(),
            topics=(),
            impact_level=ImpactLevel.LOW,
            thumbnail_url=None,
            document_url=None,
            video_id=None,
            collected_at=collected,
            evidence_status="verified_source",
        )


def test_youtube_atom_metadata_parser() -> None:
    records = parse_youtube_feed(_youtube_feed())
    assert len(records) == 1
    assert records[0].video_id == "abcdefghijk"
    assert (
        records[0].thumbnail_url == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    )


def test_official_page_image_prefers_open_graph_then_twitter() -> None:
    metadata = parse_page_image_metadata(
        b"""<head>
        <meta name="twitter:image" content="/twitter.jpg">
        <meta property="og:image" content="https://cdn.example.test/og.jpg">
        </head>""",
        page_url="https://official.example/article",
    )

    assert metadata is not None
    assert metadata.image_url == "https://cdn.example.test/og.jpg"
    assert metadata.image_source == "og:image"


def test_feed_generation_deduplicates_urls_and_records_provider_failure(
    tmp_path: Path,
) -> None:
    external_path, analytics_path, config_path, output_path = _inputs(tmp_path)
    generated = datetime(2026, 8, 1, 12, tzinfo=UTC)
    govdata_url = "https://data.example.test/search?year=2026"
    acea_url = "https://official.example/report-page"
    youtube_url = "https://www.youtube.com/feeds/videos.xml?user=BMWGroup"
    result = build_content_feed(
        external_input=external_path,
        analytics_input=analytics_path,
        config_path=config_path,
        output_path=output_path,
        generated_at=generated,
        fetcher=FakeFetcher(
            {
                govdata_url: _govdata_report(),
                acea_url: _official_report_page(),
                youtube_url: _youtube_feed(),
            }
        ),
    )
    assert result.status == "completed"
    assert (result.news_count, result.report_count, result.video_count) == (1, 2, 1)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len({item["source_url"] for item in payload["items"]}) == 4
    assert all(
        item["evidence_status"] == "verified_source" for item in payload["items"]
    )
    newsroom = next(
        item for item in payload["items"] if item["source_name"] == "Official newsroom"
    )
    assert newsroom["thumbnail_url"] == "https://official.example/news/cover.jpg"

    failure_dir = tmp_path / "failure"
    failure_dir.mkdir()
    failed_external, failed_analytics, failed_config, failed_output = _inputs(
        failure_dir
    )
    failed = build_content_feed(
        external_input=failed_external,
        analytics_input=failed_analytics,
        config_path=failed_config,
        output_path=failed_output,
        generated_at=generated,
        fetcher=FakeFetcher(),
    )
    assert failed.status == "completed"
    assert failed.news_count == 1
    assert failed.report_count == failed.video_count == 0
    assert {status["status"] for status in failed.source_statuses} >= {"failed"}


def test_all_provider_failure_preserves_previous_content_feed(tmp_path: Path) -> None:
    external_path, analytics_path, config_path, output_path = _inputs(tmp_path)
    external = json.loads(external_path.read_text(encoding="utf-8"))
    external["news"]["articles"] = []
    external["brand_news"]["articles"] = []
    external["sources"] = [
        {
            "source": "Official newsroom",
            "status": "failed",
            "cache_status": None,
            "record_count": 0,
        }
    ]
    external_path.write_text(json.dumps(external), encoding="utf-8")
    output_path.write_text("old valid content feed", encoding="utf-8")

    result = build_content_feed(
        external_input=external_path,
        analytics_input=analytics_path,
        config_path=config_path,
        output_path=output_path,
        generated_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        fetcher=FakeFetcher(),
    )

    assert result.status == "failed"
    assert output_path.read_text(encoding="utf-8") == "old valid content feed"


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    analytics = {
        "date": "2026-08-01",
        "vehicles": [
            {
                "vehicle": {"brand": "BMW", "model": "iX1"},
                "metrics": {},
                "opportunity_score": {},
            }
        ],
        "brands": [],
        "methodology": {},
    }
    article = {
        "article_id": "a",
        "title": "BMW iX1 market update",
        "summary": "Official short summary.",
        "url": "https://official.example/news/1",
        "source": "Official newsroom",
        "source_url": "https://official.example/news",
        "published_at": "2026-07-31T10:00:00+00:00",
        "brands": ["BMW"],
        "models": ["BMW iX1"],
        "country": "DE",
        "tags": ["electric"],
        "official_brand_news": True,
        "image_url": "https://official.example/news/cover.jpg",
        "image_source": "rss_media_content",
    }
    external = {
        "report_date": "2026-08-01",
        "generated_at": "2026-08-01T11:00:00+00:00",
        "news": {"articles": [article]},
        "brand_news": {"articles": [article]},
        "sources": [
            {
                "source": "Official newsroom",
                "status": "available",
                "cache_status": "refreshed",
                "record_count": 1,
            }
        ],
    }
    analytics_path = tmp_path / "analytics.json"
    external_path = tmp_path / "external.json"
    config_path = tmp_path / "content.yaml"
    output_path = tmp_path / "content_feed.json"
    analytics_path.write_text(json.dumps(analytics), encoding="utf-8")
    external_path.write_text(json.dumps(external), encoding="utf-8")
    config_path.write_text(
        """
output_path: ignored.json
cache_directory: CACHE_DIRECTORY
max_items_per_source: 20
http:
  timeout_seconds: 1
  max_bytes: 100000
  user_agent: Test
reports:
  - source_id: govdata
    provider: govdata_ckan
    source_name: GovData KBA
    source_url_template: https://data.example.test/search?year={year}
    region: DE
    language: de
    ttl_seconds: 60
  - source_id: acea_report
    provider: official_page
    source_name: ACEA
    source_url: https://official.example/report-page
    region: EU
    language: en
    ttl_seconds: 60
videos:
  - source_id: bmw_video
    source_name: BMW Group
    feed_url: https://www.youtube.com/feeds/videos.xml?user=BMWGroup
    region: GLOBAL
    language: en
    brand: BMW
    ttl_seconds: 60
""".replace("CACHE_DIRECTORY", str(tmp_path / "cache").replace("\\", "/")),
        encoding="utf-8",
    )
    return external_path, analytics_path, config_path, output_path


def _govdata_report() -> bytes:
    return json.dumps(
        {
            "result": {
                "results": [
                    {
                        "name": "kba-fz10-2026",
                        "title": "KBA FZ10 2026 registrations",
                        "notes": "Official registration dataset.",
                        "metadata_modified": "2026-07-30T12:00:00+00:00",
                        "resources": [
                            {
                                "format": "XLSX",
                                "url": "https://kba.example.test/fz10.xlsx",
                            }
                        ],
                    }
                ]
            }
        }
    ).encode()


def _youtube_feed() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <entry>
    <yt:videoId>abcdefghijk</yt:videoId>
    <title>BMW iX1 official overview</title>
    <published>2026-07-31T09:00:00+00:00</published>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/>
    <media:group>
      <media:description>Official vehicle video metadata.</media:description>
      <media:thumbnail url="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"/>
    </media:group>
  </entry>
</feed>"""


def _official_report_page() -> bytes:
    return b"""<html><head><script type="application/ld+json">
{
  "@type": "Article",
  "headline": "ACEA official market report",
  "description": "Official report metadata.",
  "url": "https://official.example/report-page",
  "datePublished": "2026-07-20T08:00:00+00:00",
  "keywords": ["market", "registrations"]
}
</script></head><body></body></html>"""
