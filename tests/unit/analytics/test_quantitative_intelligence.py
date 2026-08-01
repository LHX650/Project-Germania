"""Formula, missing-data, and boundary tests for Phase 11 models."""

from __future__ import annotations

import pytest

from germania.analytics.quantitative_intelligence import (
    VehicleQuantitativeInput,
    calculate_market_quantitative_scores,
    classify_market_momentum,
)


def test_three_model_formulas_publish_components_and_weights() -> None:
    scores = calculate_market_quantitative_scores((_vehicle(),))[0]

    assert scores.price_pressure.score == pytest.approx(58.5)
    assert scores.price_pressure.components == {
        "price_decline_7d": 50.0,
        "price_decline_30d": 20.0,
        "inventory_growth": 100.0,
        "price_dispersion": 40.0,
    }
    assert sum(scores.price_pressure.applied_weights.values()) == pytest.approx(1)

    assert scores.inventory_pressure.score == pytest.approx(57.5)
    assert scores.inventory_pressure.components["inventory_level"] == 50
    assert scores.inventory_pressure.components["low_market_activity"] == 40

    assert scores.market_momentum.score == pytest.approx(55.78)
    assert scores.market_momentum.label == "Neutral"
    assert scores.market_momentum.components["price_opportunity_trend"] == 72


def test_missing_required_data_returns_null_without_imputation() -> None:
    vehicle = _vehicle(
        price_change_7d_pct=None,
        price_change_30d_pct=None,
        market_activity_score=None,
    )

    scores = calculate_market_quantitative_scores((vehicle,))[0]

    assert scores.price_pressure.score is None
    assert scores.price_pressure.status == "insufficient_data"
    assert "price_decline_7d" in scores.price_pressure.missing_inputs
    assert scores.inventory_pressure.score is None
    assert scores.inventory_pressure.status == "insufficient_data"
    assert scores.market_momentum.score is None
    assert scores.market_momentum.label is None


def test_optional_30d_price_change_is_excluded_and_weights_are_renormalized() -> None:
    vehicle = _vehicle(price_change_30d_pct=None)

    score = calculate_market_quantitative_scores((vehicle,))[0].price_pressure

    assert score.status == "available"
    assert score.components["price_decline_30d"] is None
    assert score.applied_weights == {
        "price_decline_7d": pytest.approx(0.4118),
        "inventory_growth": pytest.approx(0.3529),
        "price_dispersion": pytest.approx(0.2353),
    }


def test_extreme_values_are_clamped_and_momentum_bands_cover_boundaries() -> None:
    vehicle = _vehicle(
        price_change_7d_pct=-1000,
        price_change_30d_pct=-1000,
        inventory_change_7d_pct=1000,
        opportunity_score=1000,
        market_activity_score=-100,
        maximum_price_eur=1_000_000,
    )
    scores = calculate_market_quantitative_scores((vehicle,))[0]

    for index in (
        scores.price_pressure,
        scores.inventory_pressure,
        scores.market_momentum,
    ):
        assert index.score is not None
        assert 0 <= index.score <= 100
        assert all(
            value is None or 0 <= value <= 100 for value in index.components.values()
        )

    assert classify_market_momentum(100) == "Strong Positive"
    assert classify_market_momentum(80) == "Strong Positive"
    assert classify_market_momentum(60) == "Positive"
    assert classify_market_momentum(40) == "Neutral"
    assert classify_market_momentum(20) == "Negative"
    assert classify_market_momentum(0) == "Strong Negative"
    with pytest.raises(ValueError, match="between 0 and 100"):
        classify_market_momentum(101)


def test_peer_inventory_normalization_and_invalid_population() -> None:
    low = _vehicle(vehicle_key="low", active_listing_count=10)
    high = _vehicle(vehicle_key="high", active_listing_count=110)

    scores = calculate_market_quantitative_scores((low, high))

    assert scores[0].inventory_pressure.components["inventory_level"] == 0
    assert scores[1].inventory_pressure.components["inventory_level"] == 100
    with pytest.raises(ValueError, match="unique"):
        calculate_market_quantitative_scores((low, low))
    with pytest.raises(ValueError, match="non-negative"):
        calculate_market_quantitative_scores((_vehicle(active_listing_count=-1),))


def _vehicle(**overrides: object) -> VehicleQuantitativeInput:
    values: dict[str, object] = {
        "vehicle_key": "Dynamic Motors Alpha",
        "active_listing_count": 100,
        "average_price_eur": 50_000,
        "minimum_price_eur": 40_000,
        "maximum_price_eur": 60_000,
        "price_change_7d_pct": -5,
        "price_change_30d_pct": -3,
        "new_listings_count_7d": 20,
        "inventory_change_7d_count": 20,
        "inventory_change_7d_pct": 25,
        "opportunity_score": 70,
        "market_activity_score": 60,
    }
    values.update(overrides)
    return VehicleQuantitativeInput(**values)  # type: ignore[arg-type]
