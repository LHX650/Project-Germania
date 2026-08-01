from __future__ import annotations

import pytest

from germania.analytics.comparable_benchmarking import (
    ComparableVehicleInput,
    calculate_comparable_vehicle_benchmarks,
    segment_family,
)


def test_exact_peer_group_gaps_rank_percentile_and_signals() -> None:
    target = _vehicle(
        "Target",
        price=50_000,
        inventory=100,
        trend=-2,
        opportunity=80,
        price_pressure=30,
        inventory_pressure=40,
        momentum=75,
    )
    peers = (
        _vehicle(
            "Peer A",
            price=45_000,
            inventory=80,
            trend=-4,
            opportunity=60,
            price_pressure=50,
            inventory_pressure=60,
            momentum=55,
        ),
        _vehicle(
            "Peer B",
            price=55_000,
            inventory=120,
            trend=0,
            opportunity=70,
            price_pressure=40,
            inventory_pressure=50,
            momentum=65,
        ),
    )

    result = calculate_comparable_vehicle_benchmarks((target, *peers))[0]

    assert result.status == "ok"
    assert result.match_level == 1
    assert result.sample_size == 2
    assert result.metrics["price_gap_pct"].peer_median == 50_000
    assert result.metrics["price_gap_pct"].gap == 0
    assert result.metrics["inventory_gap_pct"].gap == 0
    assert result.metrics["price_trend_gap_pp"].gap == 0
    assert result.metrics["opportunity_score_gap"].gap == 15
    assert result.metrics["price_pressure_gap"].gap == -15
    assert result.peer_rank == 1
    assert result.peer_percentile == 100
    assert "Opportunity Score 高于同类中位数" in result.advantages
    assert "Price Pressure 低于同类中位数" in result.advantages


def test_matching_relaxes_price_then_segment_family_without_vehicle_mapping() -> None:
    price_target = _vehicle("Target", price=50_000)
    price_peers = (
        _vehicle("Near", price=55_000),
        _vehicle("Wider", price=65_000),
    )
    price_result = calculate_comparable_vehicle_benchmarks(
        (price_target, *price_peers)
    )[0]

    assert price_result.match_level == 2
    assert "asking-price distance <= 35%" in price_result.match_basis

    family_target = _vehicle(
        "Family Target",
        price=40_000,
        segment="compact_electric_suv",
    )
    family_peers = (
        _vehicle("Family A", price=38_000, segment="compact_suv"),
        _vehicle("Family B", price=44_000, segment="compact_suv"),
    )
    family_result = calculate_comparable_vehicle_benchmarks(
        (family_target, *family_peers)
    )[0]

    assert segment_family("compact_electric_suv") == "compact_suv"
    assert family_result.match_level == 3
    assert "similar segment family" in family_result.match_basis


def test_missing_controls_and_small_group_return_insufficient_data() -> None:
    missing = _vehicle("Missing", segment=None)
    valid_a = _vehicle("Valid A")
    valid_b = _vehicle("Valid B")
    results = calculate_comparable_vehicle_benchmarks((missing, valid_a, valid_b))

    assert results[0].status == "insufficient_data"
    assert results[0].reason == "missing: vehicle_segment"
    assert results[0].metrics == {}

    only_one_peer = calculate_comparable_vehicle_benchmarks(
        (_vehicle("One"), _vehicle("Two"))
    )[0]
    assert only_one_peer.status == "insufficient_data"
    assert "fewer than two peers" in str(only_one_peer.reason)


def test_missing_metric_and_zero_peer_median_do_not_create_fake_gaps() -> None:
    target = _vehicle("Target", inventory=10, trend=None)
    peers = (
        _vehicle("Peer A", inventory=0, trend=None),
        _vehicle("Peer B", inventory=0, trend=None),
    )
    result = calculate_comparable_vehicle_benchmarks((target, *peers))[0]

    assert result.metrics["inventory_gap_pct"].peer_median == 0
    assert result.metrics["inventory_gap_pct"].gap is None
    assert result.metrics["price_trend_gap_pp"].target_value is None
    assert result.metrics["price_trend_gap_pp"].peer_median is None
    assert result.metrics["price_trend_gap_pp"].gap is None
    assert result.metrics["price_trend_gap_pp"].rank is None


def test_rank_boundaries_and_invalid_inputs() -> None:
    target = _vehicle("Target", opportunity=10)
    peers = (
        _vehicle("Peer A", opportunity=20),
        _vehicle("Peer B", opportunity=30),
    )
    result = calculate_comparable_vehicle_benchmarks((target, *peers))[0]

    assert result.peer_rank == 3
    assert result.peer_percentile == 0

    with pytest.raises(ValueError, match="unique"):
        calculate_comparable_vehicle_benchmarks((target, target))
    with pytest.raises(ValueError, match="positive"):
        calculate_comparable_vehicle_benchmarks((_vehicle("Bad", price=0),))


def _vehicle(
    model: str,
    *,
    price: float | None = 50_000,
    segment: str | None = "compact_suv",
    body_type: str | None = "suv",
    powertrain: str | None = "battery_electric",
    inventory: float | None = 100,
    trend: float | None = -2,
    opportunity: float | None = 60,
    price_pressure: float | None = 50,
    inventory_pressure: float | None = 50,
    momentum: float | None = 50,
) -> ComparableVehicleInput:
    return ComparableVehicleInput(
        vehicle_key=f"Test {model}",
        brand="Test",
        model=model,
        average_price_eur=price,
        vehicle_segment=segment,
        body_type=body_type,
        powertrain=powertrain,
        active_inventory=inventory,
        price_change_7d_pct=trend,
        opportunity_score=opportunity,
        price_pressure=price_pressure,
        inventory_pressure=inventory_pressure,
        market_momentum=momentum,
    )
