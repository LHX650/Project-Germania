"""AppTest coverage for Phase 12 comparable-vehicle views."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_DIR.parent
REAL_ARTIFACTS_AVAILABLE = (
    PROJECT_ROOT / "reports" / "daily_market_intelligence.json"
).is_file() and (PROJECT_ROOT / "database" / "project_germania_live.sqlite3").is_file()


def test_vehicle_analysis_renders_peer_group_median_rank_and_chart(
    tmp_path: Path,
) -> None:
    app = AppTest.from_string(
        _page_source(_write_report(tmp_path), "vehicle_analysis"),
        default_timeout=10,
    ).run()

    assert not app.exception
    assert "Peer Benchmark" in [item.value for item in app.subheader]
    labels = [metric.label for metric in app.metric]
    assert "Peer count" in labels
    assert "Peer Rank" in labels
    assert "Peer Percentile" in labels
    assert "Match level" in labels
    for gap_label in (
        "Price Gap",
        "Inventory Gap",
        "Opportunity Gap",
        "Price Pressure Gap",
        "Inventory Pressure Gap",
        "Momentum Gap",
    ):
        assert gap_label in labels
    assert any("Peer Group" in str(item.value) for item in app.markdown)
    assert any("Peer vehicles" in str(item.value) for item in app.markdown)
    assert len(app.get("vega_lite_chart")) >= 6
    captions = [item.value for item in app.caption]
    for label in (
        "Average asking price",
        "Active listing inventory",
        "Opportunity Score",
        "Market Momentum",
        "Price Pressure",
        "Inventory Pressure",
    ):
        assert any(
            label in caption and "Peer Median" in caption for caption in captions
        )


def test_vehicle_intelligence_renders_peer_first_summary(tmp_path: Path) -> None:
    app = AppTest.from_string(
        _page_source(_write_report(tmp_path), "vehicle_intelligence"),
        default_timeout=10,
    ).run()

    assert not app.exception
    assert "Peer Benchmarking" in [item.value for item in app.subheader]
    assert "Peer count" in [metric.label for metric in app.metric]
    assert any("exact vehicle_segment" in item.value for item in app.caption)


def test_price_and_brand_pages_render_comparable_views(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path)
    price_app = AppTest.from_string(
        _page_source(report_path, "price_intelligence"),
        default_timeout=10,
    ).run()
    brand_app = AppTest.from_string(
        _page_source(report_path, "brand_competition"),
        default_timeout=10,
    ).run()

    assert not price_app.exception
    assert "Peer asking-price benchmark" in [item.value for item in price_app.subheader]
    assert any("dynamic Peer Median" in item.value for item in price_app.caption)
    assert not brand_app.exception
    assert "Comparable vehicle positioning" in {
        item.label for item in brand_app.expander
    }
    assert any(
        "Brand vehicle peer benchmarks" in str(item.value)
        for item in brand_app.markdown
    )
    assert any("dynamic Peer Group" in item.value for item in brand_app.caption)


def test_missing_segment_is_explicitly_insufficient_data(tmp_path: Path) -> None:
    app = AppTest.from_string(
        _page_source(
            _write_report(tmp_path),
            "vehicle_analysis",
            missing_segment=True,
        ),
        default_timeout=10,
    ).run()

    assert not app.exception
    assert any("insufficient_data" in item.value for item in app.info)
    assert any("Segment missing" in item.value for item in app.caption)


@pytest.mark.skipif(
    not REAL_ARTIFACTS_AVAILABLE,
    reason="real read-only Analytics/SQLite artifacts are not present",
)
def test_real_tesla_model_y_peer_benchmark_is_visible() -> None:
    app = AppTest.from_string(_real_vehicle_analysis_source(), default_timeout=15).run()
    app.selectbox(key="vehicle_analysis_brand").select("Tesla").run()
    app.selectbox(key="vehicle_analysis_model").select("Model Y").run()

    assert not app.exception
    assert "Peer Benchmark" in [item.value for item in app.subheader]
    metrics = {metric.label: metric.value for metric in app.metric}
    peer_count = int(metrics["Peer count"])
    assert peer_count >= 2
    assert metrics["Match level"].startswith("Level ")
    assert metrics["Peer Rank"].startswith("#")
    assert metrics["Peer Rank"].endswith(f"/{peer_count + 1}")
    assert metrics["Peer Percentile"].endswith("%")
    assert all(
        label in metrics
        for label in (
            "Price Gap",
            "Inventory Gap",
            "Opportunity Gap",
            "Price Pressure Gap",
            "Inventory Pressure Gap",
            "Momentum Gap",
        )
    )
    assert len(app.get("vega_lite_chart")) >= 5
    assert any("Peer vehicles" in str(item.value) for item in app.markdown)


def _page_source(
    report_path: Path,
    page_name: str,
    *,
    missing_segment: bool = False,
) -> str:
    page_setup = ""
    if page_name == "vehicle_analysis":
        page_setup = """
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
from services.database import ComparableVehicleMetadata
from services.peer_benchmarking import PeerBenchmarkReport
from germania.analytics.comparable_benchmarking import (
    ComparableVehicleInput,
    calculate_comparable_vehicle_benchmarks,
)
from pages import {page_name} as page
{page_setup}
def peer_fixture(report):
    metadata = tuple(
        ComparableVehicleMetadata(
            vehicle_key=f"{{vehicle.brand}} {{vehicle.model}}",
            brand_name=vehicle.brand,
            model_name=vehicle.model,
            vehicle_segment={"None" if missing_segment else "'compact_electric_suv'"},
            body_type="suv",
            powertrain="battery_electric",
            market_attribute="fixture",
        )
        for vehicle in report.vehicles
    )
    inputs = []
    for vehicle in report.vehicles:
        key = f"{{vehicle.brand}} {{vehicle.model}}"
        scores = report.quantitative_by_vehicle[key]
        controls = next(item for item in metadata if item.vehicle_key == key)
        inputs.append(ComparableVehicleInput(
            vehicle_key=key,
            brand=vehicle.brand,
            model=vehicle.model,
            average_price_eur=vehicle.metrics.average_price_eur,
            vehicle_segment=controls.vehicle_segment,
            body_type=controls.body_type,
            powertrain=controls.powertrain,
            active_inventory=vehicle.metrics.active_listing_count,
            price_change_7d_pct=vehicle.metrics.price_change_7d_pct,
            opportunity_score=vehicle.opportunity_score.score,
            price_pressure=scores.price_pressure.score,
            inventory_pressure=scores.inventory_pressure.score,
            market_momentum=scores.market_momentum.score,
        ))
    return PeerBenchmarkReport(
        benchmarks=calculate_comparable_vehicle_benchmarks(tuple(inputs)),
        metadata=metadata,
    )
page.load_peer_benchmarks = peer_fixture
report = load_daily_market_intelligence({str(report_path)!r})
page.render(report)
"""


def _real_vehicle_analysis_source() -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
from services.intelligence import load_daily_market_intelligence
from services.peer_benchmarking import load_peer_benchmarks
from pages import vehicle_analysis as page
page.load_peer_benchmarks = load_peer_benchmarks
page.render(load_daily_market_intelligence())
"""


def _write_report(tmp_path: Path) -> Path:
    path = tmp_path / "daily_market_intelligence.json"
    vehicles = [
        _vehicle("Alpha", 50_000, 100, -2, 80),
        _vehicle("Beta", 47_000, 80, -4, 60),
        _vehicle("Gamma", 54_000, 120, 0, 70),
    ]
    payload = {
        "date": "2026-08-01",
        "vehicles": vehicles,
        "brands": [
            {
                "brand": "Dynamic Motors",
                "metrics": {
                    "active_inventory_count": 300,
                    "active_inventory_rank": 1,
                    "average_vehicle_price_eur": 50_333.33,
                    "bev_share_pct": 100,
                    "phev_share_pct": 0,
                    "bev_phev_share_pct": 100,
                    "model_coverage_count": 3,
                    "catalog_model_count": 3,
                    "model_coverage_pct": 100,
                },
            }
        ],
        "methodology": {"scope": "fixture"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _vehicle(
    model: str,
    average: int,
    active: int,
    price_7d: float,
    opportunity: float,
) -> dict[str, object]:
    return {
        "vehicle": {"brand": "Dynamic Motors", "model": model},
        "metrics": {
            "active_listing_count": active,
            "average_price_eur": average,
            "minimum_price_eur": average * 0.8,
            "maximum_price_eur": average * 1.2,
            "price_change_7d_pct": price_7d,
            "price_change_30d_pct": price_7d / 2,
            "new_listings_count_7d": 20,
            "inventory_change_7d_count": 10,
            "inventory_change_7d_pct": 10,
        },
        "opportunity_score": {
            "score": opportunity,
            "components": {
                "inventory_attractiveness": 50,
                "price_competitiveness": 50,
                "price_trend": 50,
                "market_activity": 60,
            },
            "applied_weights": {
                "inventory_attractiveness": 0.3,
                "price_competitiveness": 0.3,
                "price_trend": 0.2,
                "market_activity": 0.2,
            },
        },
    }
