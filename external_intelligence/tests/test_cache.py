from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.http import HTTPResponse


@dataclass
class CountingFetcher:
    body: bytes = b"first"
    calls: list[dict[str, str]] = field(default_factory=list)
    fail: bool = False

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        self.calls.append(headers or {})
        if self.fail:
            raise TimeoutError("offline fixture")
        return HTTPResponse(
            self.body,
            200,
            "application/xml",
            etag='"fixture-etag"',
        )


def test_cache_avoids_duplicate_download_within_ttl(tmp_path: Path) -> None:
    cache = ExternalIntelligenceCache(tmp_path / "cache")
    fetcher = CountingFetcher()
    now = datetime(2026, 7, 31, tzinfo=UTC)

    first = cache.get_or_fetch(
        source_id="fixture",
        source_url="https://example.test/feed.xml",
        ttl_seconds=3600,
        fetcher=fetcher,
        now=now,
    )
    second = cache.get_or_fetch(
        source_id="fixture",
        source_url="https://example.test/feed.xml",
        ttl_seconds=3600,
        fetcher=fetcher,
        now=now + timedelta(minutes=5),
    )

    assert first.cache_status == "refreshed"
    assert second.cache_status == "hit"
    assert second.payload_path.read_bytes() == b"first"
    assert len(fetcher.calls) == 1


def test_expired_cache_is_used_when_refresh_fails(tmp_path: Path) -> None:
    cache = ExternalIntelligenceCache(tmp_path / "cache")
    fetcher = CountingFetcher()
    now = datetime(2026, 7, 31, tzinfo=UTC)
    cache.get_or_fetch(
        source_id="fixture",
        source_url="https://example.test/feed.xml",
        ttl_seconds=60,
        fetcher=fetcher,
        now=now,
    )
    fetcher.fail = True

    stale = cache.get_or_fetch(
        source_id="fixture",
        source_url="https://example.test/feed.xml",
        ttl_seconds=60,
        fetcher=fetcher,
        now=now + timedelta(minutes=2),
    )

    assert stale.cache_status == "stale_fallback"
    assert stale.fetched_at == now
    assert len(fetcher.calls) == 2
