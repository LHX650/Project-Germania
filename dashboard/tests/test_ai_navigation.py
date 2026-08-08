"""Tests for Phase 16 visible navigation and retained fallback routes."""

from __future__ import annotations

from app import (
    AI_PAGE_RENDERERS,
    CONTENT_PAGE_RENDERERS,
    INTELLIGENCE_PAGE_RENDERERS,
    STATIC_PAGE_RENDERERS,
)
from components.navigation import (
    AI_MARKET_INSIGHTS,
    BRAND_COMPETITION,
    DATA_QUALITY,
    EXECUTIVE_OVERVIEW,
    GLOBAL_INTELLIGENCE_HUB,
    HIDDEN_PAGE_NAMES,
    MARKET_ALERTS,
    MARKET_ANALYSIS,
    MARKET_MONITOR,
    NAVIGATION_GROUPS,
    PAGE_NAMES,
    PRICE_INTELLIGENCE,
    SEARCH_CENTER,
    VEHICLE_ANALYSIS,
    VEHICLE_INTELLIGENCE,
)


def test_navigation_contains_exactly_nine_grouped_core_pages() -> None:
    assert PAGE_NAMES == (
        EXECUTIVE_OVERVIEW,
        GLOBAL_INTELLIGENCE_HUB,
        MARKET_ALERTS,
        VEHICLE_INTELLIGENCE,
        BRAND_COMPETITION,
        PRICE_INTELLIGENCE,
        VEHICLE_ANALYSIS,
        SEARCH_CENTER,
        DATA_QUALITY,
    )
    assert tuple(page for _, pages in NAVIGATION_GROUPS for page in pages) == PAGE_NAMES
    assert [name for name, _ in NAVIGATION_GROUPS] == [
        "📊 Executive",
        "🌍 Market Intelligence",
        "🔍 Deep Analysis",
        "⚙️ Platform",
    ]


def test_hidden_pages_keep_renderer_fallback_without_visible_navigation() -> None:
    assert HIDDEN_PAGE_NAMES == (
        AI_MARKET_INSIGHTS,
        MARKET_MONITOR,
        MARKET_ANALYSIS,
    )
    assert not set(HIDDEN_PAGE_NAMES).intersection(PAGE_NAMES)
    assert AI_MARKET_INSIGHTS in AI_PAGE_RENDERERS
    assert MARKET_MONITOR in STATIC_PAGE_RENDERERS
    assert MARKET_ANALYSIS in STATIC_PAGE_RENDERERS
    assert MARKET_ALERTS in INTELLIGENCE_PAGE_RENDERERS


def test_global_intelligence_hub_remains_registered() -> None:
    assert GLOBAL_INTELLIGENCE_HUB in CONTENT_PAGE_RENDERERS
