from __future__ import annotations

import json
from pathlib import Path

import pytest
from services.intelligence import (
    IntelligenceReportError,
    clear_intelligence_cache,
    load_daily_market_intelligence,
)


def test_loads_valid_dynamic_intelligence_report(tmp_path: Path) -> None:
    report_path = tmp_path / "daily_market_intelligence.json"
    _write_report(report_path)

    report = load_daily_market_intelligence(report_path)

    assert report.report_date.isoformat() == "2026-07-31"
    assert report.active_inventory_count == 3
    assert report.new_listings_count_7d == 2
    assert report.weighted_average_price_eur == pytest.approx(30_000)
    assert [item.model for item in report.vehicles] == ["Alpha", "Beta"]
    assert report.brands[0].brand == "Dynamic Motors"
    assert len(report.quantitative_scores) == 2
    assert report.quantitative_scores[0].inventory_pressure.score is not None
    assert report.quantitative_scores[0].market_momentum.label is not None
    assert report.source_path == report_path.resolve()


def test_missing_and_invalid_reports_fail_clearly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(IntelligenceReportError, match="was not found"):
        load_daily_market_intelligence(missing)

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"date": "not-a-date"}', encoding="utf-8")
    with pytest.raises(IntelligenceReportError, match="YYYY-MM-DD"):
        load_daily_market_intelligence(invalid)


def test_report_cache_refreshes_after_incremental_file_update(tmp_path: Path) -> None:
    report_path = tmp_path / "daily_market_intelligence.json"
    _write_report(report_path, first_inventory=1)
    first = load_daily_market_intelligence(report_path)

    _write_report(report_path, first_inventory=10)
    second = load_daily_market_intelligence(report_path)

    assert first.active_inventory_count == 3
    assert second.active_inventory_count == 12
    assert first is not second


def test_empty_report_remains_explicitly_empty(tmp_path: Path) -> None:
    report_path = tmp_path / "empty.json"
    report_path.write_text(
        json.dumps(
            {
                "date": "2026-07-31",
                "vehicles": [],
                "brands": [],
                "methodology": {},
            }
        ),
        encoding="utf-8",
    )

    report = load_daily_market_intelligence(report_path)

    assert report.vehicles == ()
    assert report.brands == ()
    assert report.quantitative_scores == ()
    assert report.active_inventory_count == 0
    assert report.weighted_average_price_eur is None


@pytest.fixture(autouse=True)
def clear_cache_between_tests() -> None:
    clear_intelligence_cache()


def _write_report(path: Path, *, first_inventory: int = 1) -> None:
    payload = {
        "date": "2026-07-31",
        "vehicles": [
            _vehicle("Alpha", first_inventory, 20_000, 1, 80),
            _vehicle("Beta", 2, 35_000, 1, 65),
        ],
        "brands": [
            {
                "brand": "Dynamic Motors",
                "metrics": {
                    "active_inventory_count": first_inventory + 2,
                    "active_inventory_rank": 1,
                    "average_vehicle_price_eur": 30_000,
                    "bev_share_pct": 50,
                    "phev_share_pct": 25,
                    "bev_phev_share_pct": 75,
                    "model_coverage_count": 2,
                    "catalog_model_count": 2,
                    "model_coverage_pct": 100,
                },
            }
        ],
        "methodology": {
            "scope": "Test report",
            "formulas": {},
            "missing_data_rules": {},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _vehicle(
    model: str,
    inventory: int,
    price: int,
    new_listings: int,
    score: int,
) -> dict[str, object]:
    return {
        "vehicle": {"brand": "Dynamic Motors", "model": model},
        "metrics": {
            "active_listing_count": inventory,
            "average_price_eur": price,
            "minimum_price_eur": price - 1_000,
            "maximum_price_eur": price + 1_000,
            "price_change_7d_pct": None,
            "price_change_30d_pct": None,
            "new_listings_count_7d": new_listings,
            "inventory_change_7d_count": new_listings,
            "inventory_change_7d_pct": None,
        },
        "opportunity_score": {
            "score": score,
            "components": {
                "inventory_attractiveness": score,
                "price_competitiveness": score,
                "price_trend": None,
                "market_activity": score,
            },
            "applied_weights": {
                "inventory_attractiveness": 0.375,
                "price_competitiveness": 0.375,
                "market_activity": 0.25,
            },
        },
    }
