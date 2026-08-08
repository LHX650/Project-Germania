from __future__ import annotations

import json
from pathlib import Path

from services.intelligence import (
    DailyMarketIntelligence,
    clear_intelligence_cache,
    load_daily_market_intelligence,
    vehicle_key,
)
from services.market_alerts import build_market_alert_report
from services.peer_benchmarking import PeerBenchmarkReport

from germania.analytics.comparable_benchmarking import (
    ComparableVehicleInput,
    calculate_comparable_vehicle_benchmarks,
)


def test_detects_price_inventory_peer_and_opportunity_changes(
    tmp_path: Path,
) -> None:
    previous = _report(
        tmp_path / "previous.json",
        report_date="2026-08-06",
        target_price_change=0.0,
        target_inventory_change=0.0,
        target_opportunity=80.0,
        target_activity=50.0,
        target_new_listings=5,
    )
    current = _report(
        tmp_path / "current.json",
        report_date="2026-08-07",
        target_price_change=-8.0,
        target_inventory_change=40.0,
        target_opportunity=5.0,
        target_activity=0.0,
        target_new_listings=5,
    )

    result = build_market_alert_report(
        current,
        history=(previous,),
        peer_reports={
            previous.report_date: _peer_report(previous),
            current.report_date: _peer_report(current),
        },
    )

    target = [item for item in result.alerts if item.vehicle == "Target"]
    assert {item.alert_type for item in target if item.level == "Critical"} == {
        "Price Drop Alert",
        "Inventory Pressure Alert",
        "Peer Competitive Alert",
        "Opportunity Change Alert",
    }
    assert all(item.status == "available" for item in target)
    assert len(result.trend) == 2
    assert result.trend[-1].critical_count >= 4


def test_missing_inputs_return_insufficient_data_without_imputation(
    tmp_path: Path,
) -> None:
    current = _report(
        tmp_path / "missing.json",
        report_date="2026-08-07",
        target_price_change=None,
        target_inventory_change=None,
        target_opportunity=50.0,
        target_activity=50.0,
        target_new_listings=0,
    )

    result = build_market_alert_report(current)
    target = [item for item in result.alerts if item.vehicle == "Target"]

    assert len(target) == 4
    assert all(item.status == "insufficient_data" for item in target)
    assert all(item.level is None for item in target)


def test_no_abnormal_vehicle_returns_normal_or_insufficient_data(
    tmp_path: Path,
) -> None:
    current = _report(
        tmp_path / "normal.json",
        report_date="2026-08-07",
        target_price_change=0.0,
        target_inventory_change=0.0,
        target_opportunity=50.0,
        target_activity=50.0,
        target_new_listings=0,
    )

    result = build_market_alert_report(current)

    assert result.critical_count == 0
    assert result.warning_count == 0
    assert result.normal_count >= 2
    assert result.insufficient_data_count >= 2


def test_empty_analytics_report_produces_no_alerts(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text(
        json.dumps(
            {
                "date": "2026-08-07",
                "vehicles": [],
                "brands": [],
                "methodology": {},
            }
        ),
        encoding="utf-8",
    )
    report = load_daily_market_intelligence(path)

    result = build_market_alert_report(report)

    assert result.alerts == ()
    assert result.critical_count == 0
    assert result.warning_count == 0
    assert result.trend[0].insufficient_data_count == 0


def _report(
    path: Path,
    *,
    report_date: str,
    target_price_change: float | None,
    target_inventory_change: float | None,
    target_opportunity: float,
    target_activity: float,
    target_new_listings: int,
) -> DailyMarketIntelligence:
    vehicles = [
        _vehicle(
            "Target",
            active=100,
            average_price=40_000,
            price_change=target_price_change,
            inventory_change=target_inventory_change,
            new_listings=target_new_listings,
            opportunity=target_opportunity,
            activity=target_activity,
            wide_price_range=True,
        ),
        _vehicle(
            "Peer A",
            active=50,
            average_price=42_000,
            price_change=0.0,
            inventory_change=0.0,
            new_listings=2,
            opportunity=70.0,
            activity=50.0,
        ),
        _vehicle(
            "Peer B",
            active=40,
            average_price=44_000,
            price_change=0.0,
            inventory_change=0.0,
            new_listings=2,
            opportunity=60.0,
            activity=50.0,
        ),
    ]
    path.write_text(
        json.dumps(
            {
                "date": report_date,
                "vehicles": vehicles,
                "brands": [],
                "methodology": {},
            }
        ),
        encoding="utf-8",
    )
    clear_intelligence_cache()
    return load_daily_market_intelligence(path)


def _vehicle(
    model: str,
    *,
    active: int,
    average_price: float,
    price_change: float | None,
    inventory_change: float | None,
    new_listings: int,
    opportunity: float,
    activity: float,
    wide_price_range: bool = False,
) -> dict[str, object]:
    return {
        "vehicle": {"brand": "Test Motors", "model": model},
        "metrics": {
            "active_listing_count": active,
            "average_price_eur": average_price,
            "minimum_price_eur": 20_000 if wide_price_range else average_price - 2_000,
            "maximum_price_eur": 60_000 if wide_price_range else average_price + 2_000,
            "price_change_7d_pct": price_change,
            "price_change_30d_pct": price_change,
            "new_listings_count_7d": new_listings,
            "inventory_change_7d_count": new_listings,
            "inventory_change_7d_pct": inventory_change,
        },
        "opportunity_score": {
            "score": opportunity,
            "components": {
                "inventory_attractiveness": opportunity,
                "price_competitiveness": opportunity,
                "price_trend": opportunity,
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


def _peer_report(report: DailyMarketIntelligence) -> PeerBenchmarkReport:
    inputs = tuple(
        ComparableVehicleInput(
            vehicle_key=vehicle_key(item.brand, item.model),
            brand=item.brand,
            model=item.model,
            average_price_eur=item.metrics.average_price_eur,
            vehicle_segment="C-SUV",
            body_type="SUV",
            powertrain="BEV",
            active_inventory=float(item.metrics.active_listing_count),
            price_change_7d_pct=item.metrics.price_change_7d_pct,
            opportunity_score=item.opportunity_score.score,
            price_pressure=report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].price_pressure.score,
            inventory_pressure=report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].inventory_pressure.score,
            market_momentum=report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].market_momentum.score,
        )
        for item in report.vehicles
    )
    return PeerBenchmarkReport(
        benchmarks=calculate_comparable_vehicle_benchmarks(inputs),
        metadata=(),
    )
