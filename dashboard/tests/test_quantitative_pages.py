"""AppTest coverage for Phase 11 model integration on the four target pages."""

from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_executive_renders_quantitative_overview_and_alerts(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    app = AppTest.from_string(
        _page_source(report_path, "executive_overview"),
        default_timeout=10,
    ).run()

    assert not app.exception
    labels = [metric.label for metric in app.metric]
    assert "Price Pressure 总览" in labels
    assert "Inventory Pressure 总览" in labels
    assert "Market Momentum" in labels
    assert "Quantitative Market Signals" in [item.value for item in app.subheader]
    assert any("Risk alerts" in str(item.value) for item in app.markdown)
    assert any("Opportunity alerts" in str(item.value) for item in app.markdown)


def test_vehicle_intelligence_renders_scores_and_momentum_ranking(
    tmp_path: Path,
) -> None:
    report_path = _write_report(tmp_path)
    app = AppTest.from_string(
        _page_source(report_path, "vehicle_intelligence"),
        default_timeout=10,
    ).run()

    assert not app.exception
    labels = [metric.label for metric in app.metric]
    assert "Price Pressure Index" in labels
    assert "Inventory Pressure Index" in labels
    assert "Market Momentum Score" in labels
    assert "车型量化排名" in [item.value for item in app.subheader]
    assert any("Neutral" in str(item.value) for item in app.markdown)


def test_vehicle_analysis_renders_three_indices_when_history_is_missing(
    tmp_path: Path,
) -> None:
    report_path = _write_report(tmp_path)
    app = AppTest.from_string(
        _page_source(report_path, "vehicle_analysis"),
        default_timeout=10,
    ).run()

    assert not app.exception
    labels = [metric.label for metric in app.metric]
    assert "Price Pressure Index" in labels
    assert "Inventory Pressure Index" in labels
    assert "Market Momentum Score" in labels
    assert any("暂无可验证的车型历史观测数据" in item.value for item in app.info)


def test_price_intelligence_renders_pressure_and_linkage_views(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    app = AppTest.from_string(
        _page_source(report_path, "price_intelligence"),
        default_timeout=10,
    ).run()

    assert not app.exception
    subheaders = [item.value for item in app.subheader]
    assert "Price Pressure Ranking" in subheaders
    assert "价格变化与库存变化联动" in subheaders
    assert len(app.get("vega_lite_chart")) >= 3


def _page_source(report_path: Path, page_name: str) -> str:
    setup = ""
    if page_name == "vehicle_analysis":
        setup = """
import pages.vehicle_analysis as page
from services.content_feed import ContentFeedError
page.load_vehicle_analysis = lambda *args: None
def missing_feed():
    raise ContentFeedError("fixture feed unavailable")
page.load_content_feed = missing_feed
"""
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
from services.intelligence import load_daily_market_intelligence
from pages import {page_name} as page
{setup}
report = load_daily_market_intelligence({str(report_path)!r})
{_render_call(page_name)}
"""


def _render_call(page_name: str) -> str:
    if page_name == "executive_overview":
        return "page.render(report, ai_report=None, pipeline=None)"
    return "page.render(report)"


def _write_report(tmp_path: Path) -> Path:
    path = tmp_path / "daily_market_intelligence.json"
    payload = {
        "date": "2026-08-01",
        "vehicles": [
            _vehicle(
                "Alpha",
                active=100,
                average=50_000,
                minimum=40_000,
                maximum=60_000,
                price_7d=-5,
                price_30d=-3,
                new=20,
                inventory_count=20,
                inventory_pct=25,
                opportunity=70,
                activity=60,
            ),
            _vehicle(
                "Beta",
                active=50,
                average=30_000,
                minimum=25_000,
                maximum=35_000,
                price_7d=2,
                price_30d=None,
                new=5,
                inventory_count=-5,
                inventory_pct=-9.09,
                opportunity=45,
                activity=30,
            ),
        ],
        "brands": [],
        "methodology": {"scope": "fixture"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _vehicle(
    model: str,
    *,
    active: int,
    average: int,
    minimum: int,
    maximum: int,
    price_7d: float | None,
    price_30d: float | None,
    new: int,
    inventory_count: int,
    inventory_pct: float | None,
    opportunity: float,
    activity: float,
) -> dict[str, object]:
    return {
        "vehicle": {"brand": "Dynamic Motors", "model": model},
        "metrics": {
            "active_listing_count": active,
            "average_price_eur": average,
            "minimum_price_eur": minimum,
            "maximum_price_eur": maximum,
            "price_change_7d_pct": price_7d,
            "price_change_30d_pct": price_30d,
            "new_listings_count_7d": new,
            "inventory_change_7d_count": inventory_count,
            "inventory_change_7d_pct": inventory_pct,
        },
        "opportunity_score": {
            "score": opportunity,
            "components": {
                "inventory_attractiveness": 50,
                "price_competitiveness": 50,
                "price_trend": 50 if price_7d is not None else None,
                "market_activity": activity,
            },
            "applied_weights": {
                "inventory_attractiveness": 0.3,
                "price_competitiveness": 0.3,
                "price_trend": 0.2,
                "market_activity": 0.2,
            },
        },
    }
