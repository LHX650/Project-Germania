from __future__ import annotations

import hashlib
from datetime import UTC
from typing import Any

import pytest

from germania.collectors.autoscout24 import AutoScout24Collector, SearchConfig
from germania.collectors.exceptions import CollectorConfigurationError
from germania.config.playwright import load_playwright_config


def test_autoscout24_collector_loads_listing_page_with_mock_loader() -> None:
    html = "<html><body>mock listing page</body></html>"
    page_loader = FakePageLoader(html)
    collector = AutoScout24Collector(
        source_config=_source_config(),
        playwright_settings=load_playwright_config(environ={}),
        page_loader=page_loader,
    )

    result = collector.load_listing_page(SearchConfig(brand="Volkswagen", model="Golf"))

    assert result.html == html
    assert result.url.startswith("https://www.autoscout24.de/lst/volkswagen/golf?")
    assert result.metadata.source_id == "autoscout24_de"
    assert result.metadata.collected_at.tzinfo == UTC
    assert result.metadata.content_sha256 == hashlib.sha256(html.encode()).hexdigest()
    assert collector.request_count == 1
    assert page_loader.calls == [(result.url, 30)]


def test_autoscout24_collector_uses_source_base_url_for_search_url() -> None:
    collector = AutoScout24Collector(
        source_config=_source_config(base_url="https://autoscout24.de"),
        playwright_settings=load_playwright_config(environ={}),
        page_loader=FakePageLoader("<html></html>"),
    )

    url = collector.build_search_url(SearchConfig(brand="BMW", model="iX1"))

    assert url.startswith("https://autoscout24.de/lst/bmw/ix1?")


def test_autoscout24_collector_rejects_non_german_source_base_url() -> None:
    with pytest.raises(CollectorConfigurationError, match="German AutoScout24"):
        AutoScout24Collector(
            source_config=_source_config(base_url="https://www.autoscout24.fr"),
            playwright_settings=load_playwright_config(environ={}),
            page_loader=FakePageLoader("<html></html>"),
        )


def test_autoscout24_collector_default_collect_is_non_fetching() -> None:
    page_loader = FakePageLoader("<html></html>")
    collector = AutoScout24Collector(
        source_config=_source_config(),
        playwright_settings=load_playwright_config(environ={}),
        page_loader=page_loader,
    )

    assert collector.collect() == []
    assert page_loader.calls == []
    assert collector.request_count == 0


class FakePageLoader:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls: list[tuple[str, float]] = []

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        self.calls.append((url, timeout_seconds))
        return self.html


def _source_config(
    *,
    base_url: str = "https://www.autoscout24.de",
) -> dict[str, Any]:
    return {
        "metadata": {"schema_version": 1},
        "sources": [
            {
                "source_id": "autoscout24_de",
                "source_name": "AutoScout24 Germany",
                "source_type": "marketplace",
                "country_code": "DE",
                "base_url": base_url,
                "data_categories": ["listings"],
                "update_frequency": "daily",
                "authority_level": "primary_commercial",
                "active": True,
                "collection_method": "html_parse",
                "notes": "Unit-test source. No network request is made.",
            }
        ],
    }
