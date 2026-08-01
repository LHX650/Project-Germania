"""Tests for read-only content Feed loading, filtering, and market matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from services.content_feed import (
    ContentFeedError,
    clear_content_feed_cache,
    filter_content,
    load_content_feed,
)


def test_content_feed_loads_all_types_and_refreshes_after_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "content_feed.json"
    _write_feed(path, title="First title")
    first = load_content_feed(path)
    assert first.counts == {"news": 1, "report": 1, "video": 1}
    assert {item.content_type for item in first.items} == {"news", "report", "video"}

    _write_feed(path, title="Updated title")
    refreshed = load_content_feed(path)
    assert refreshed.items[0].title == "Updated title"
    clear_content_feed_cache()


def test_filtering_and_invalid_evidence(tmp_path: Path) -> None:
    path = tmp_path / "content_feed.json"
    _write_feed(path, title="BMW iX1 update")
    feed = load_content_feed(path)
    assert len(filter_content(feed.items, keyword="ix1", content_types=("news",))) == 1
    assert len(filter_content(feed.items, regions=("DE",), brands=("BMW",))) == 3

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["items"][0]["source_url"] = "javascript:alert(1)"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ContentFeedError, match="HTTPS"):
        load_content_feed(path)


def _write_feed(path: Path, *, title: str) -> None:
    base = {
        "title": title,
        "source_name": "Official source",
        "published_at": "2026-07-31T10:00:00+00:00",
        "summary": "Short official metadata.",
        "language": "en",
        "region": "DE",
        "brands": ["BMW"],
        "vehicles": ["BMW iX1"],
        "topics": ["electric"],
        "impact_level": "high",
        "thumbnail_url": None,
        "collected_at": "2026-08-01T11:00:00+00:00",
        "evidence_status": "verified_source",
        "ai_summary": "Rule summary.",
        "summary_mode": "local_rule_fallback",
    }
    items = [
        {
            **base,
            "content_id": "news-id",
            "content_type": "news",
            "source_url": "https://official.example/news",
            "document_url": None,
            "video_id": None,
        },
        {
            **base,
            "content_id": "report-id",
            "content_type": "report",
            "source_url": "https://official.example/report",
            "document_url": "https://official.example/report.pdf",
            "video_id": None,
        },
        {
            **base,
            "content_id": "video-id",
            "content_type": "video",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "document_url": None,
            "video_id": "abcdefghijk",
        },
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_date": "2026-08-01",
                "generated_at": "2026-08-01T12:00:00+00:00",
                "counts": {"news": 1, "report": 1, "video": 1},
                "items": items,
                "sources": [],
            }
        ),
        encoding="utf-8",
    )
