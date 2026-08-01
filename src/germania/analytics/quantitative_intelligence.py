"""Independent, explainable market-pressure and momentum models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

PRICE_PRESSURE_WEIGHTS = {
    "price_decline_7d": 0.35,
    "price_decline_30d": 0.15,
    "inventory_growth": 0.30,
    "price_dispersion": 0.20,
}
INVENTORY_PRESSURE_WEIGHTS = {
    "inventory_level": 0.35,
    "inventory_growth": 0.30,
    "new_listing_intensity": 0.20,
    "low_market_activity": 0.15,
}
MARKET_MOMENTUM_WEIGHTS = {
    "new_listing_activity": 0.25,
    "price_opportunity_trend": 0.20,
    "inventory_availability_trend": 0.15,
    "opportunity_score": 0.30,
    "market_activity": 0.10,
}

IndexStatus = Literal["available", "insufficient_data"]
MomentumLabel = Literal[
    "Strong Positive",
    "Positive",
    "Neutral",
    "Negative",
    "Strong Negative",
]


@dataclass(frozen=True)
class VehicleQuantitativeInput:
    """Existing Analytics values required by the independent models."""

    vehicle_key: str
    active_listing_count: int
    average_price_eur: float | None
    minimum_price_eur: float | None
    maximum_price_eur: float | None
    price_change_7d_pct: float | None
    price_change_30d_pct: float | None
    new_listings_count_7d: int
    inventory_change_7d_count: int
    inventory_change_7d_pct: float | None
    opportunity_score: float | None
    market_activity_score: float | None


@dataclass(frozen=True)
class QuantitativeIndex:
    """One 0-100 model result with complete component disclosure."""

    score: float | None
    status: IndexStatus
    components: dict[str, float | None]
    weights: dict[str, float]
    applied_weights: dict[str, float]
    missing_inputs: tuple[str, ...]
    component_sources: dict[str, str]


@dataclass(frozen=True)
class MomentumIndex(QuantitativeIndex):
    """Market momentum result plus a deterministic qualitative band."""

    label: MomentumLabel | None


@dataclass(frozen=True)
class VehicleQuantitativeScores:
    """All Phase 11 quantitative results for one dynamic vehicle key."""

    vehicle_key: str
    price_pressure: QuantitativeIndex
    inventory_pressure: QuantitativeIndex
    market_momentum: MomentumIndex


QUANTITATIVE_METHODOLOGY = {
    "scope": (
        "Project models based only on marketplace asking-price and listing-inventory "
        "signals. They do not represent sales, demand, or transaction prices."
    ),
    "normalization": {
        "price_decline_7d": "clamp(-price_change_7d_pct / 10 * 100, 0, 100)",
        "price_decline_30d": "clamp(-price_change_30d_pct / 15 * 100, 0, 100)",
        "inventory_growth": (
            "clamp(max(inventory_change_signal_pct, 0) / 25 * 100, 0, 100). "
            "Use Analytics inventory_change_7d_pct when available; otherwise use "
            "inventory_change_7d_count / current_active_count * 100 as a current-"
            "inventory share signal, not as a historical growth rate."
        ),
        "price_dispersion": (
            "clamp(((maximum_price - minimum_price) / average_price) / 1.0 * 100, "
            "0, 100); this is cross-sectional asking-price dispersion."
        ),
        "inventory_level": (
            "0-100 min-max score across vehicles in the same daily Analytics report; "
            "50 when all observed counts are equal."
        ),
        "new_listing_intensity": (
            "clamp(new_listings_count_7d / max(active_listing_count, 1) * 100, "
            "0, 100)."
        ),
        "price_opportunity_trend": (
            "clamp(50 - 5 * price_change_pct, 0, 100); blend 7d/30d at 70/30 "
            "when both exist, otherwise use the available horizon."
        ),
        "inventory_availability_trend": (
            "clamp(50 + 0.5 * inventory_change_signal_pct, 0, 100)."
        ),
    },
    "models": {
        "price_pressure_index": {
            "formula": "weighted mean of available normalized components",
            "weights": PRICE_PRESSURE_WEIGHTS,
            "required": (
                "7d price change plus at least two of 30d price change, inventory "
                "change, and price dispersion"
            ),
        },
        "inventory_pressure_index": {
            "formula": "weighted mean of all four normalized components",
            "weights": INVENTORY_PRESSURE_WEIGHTS,
            "required": (
                "inventory level, inventory change, new-listing intensity, and the "
                "existing Opportunity Score market-activity component"
            ),
        },
        "market_momentum_score": {
            "formula": "weighted mean of available normalized components",
            "weights": MARKET_MOMENTUM_WEIGHTS,
            "required": (
                "new-listing activity, inventory trend, Opportunity Score, and "
                "market activity; price trend is optional"
            ),
            "bands": {
                "Strong Positive": "80-100",
                "Positive": "60-<80",
                "Neutral": "40-<60",
                "Negative": "20-<40",
                "Strong Negative": "0-<20",
            },
        },
    },
    "missing_data": (
        "Return score=null and status=insufficient_data when required inputs are "
        "missing. Optional missing components are excluded and published weights "
        "are renormalized across available components; no value is imputed."
    ),
}


def calculate_market_quantitative_scores(
    vehicles: tuple[VehicleQuantitativeInput, ...],
) -> tuple[VehicleQuantitativeScores, ...]:
    """Calculate all three models for a dynamic daily vehicle population."""

    _validate_vehicle_keys(vehicles)
    inventory_levels = _min_max_inventory_scores(vehicles)
    return tuple(
        _calculate_vehicle_scores(vehicle, inventory_levels[vehicle.vehicle_key])
        for vehicle in vehicles
    )


def classify_market_momentum(score: float) -> MomentumLabel:
    """Return the deterministic five-band label for a valid 0-100 score."""

    numeric = _finite(score)
    if numeric is None or not 0 <= numeric <= 100:
        raise ValueError("momentum score must be finite and between 0 and 100")
    if numeric >= 80:
        return "Strong Positive"
    if numeric >= 60:
        return "Positive"
    if numeric >= 40:
        return "Neutral"
    if numeric >= 20:
        return "Negative"
    return "Strong Negative"


def _calculate_vehicle_scores(
    vehicle: VehicleQuantitativeInput,
    inventory_level_score: float,
) -> VehicleQuantitativeScores:
    inventory_change, inventory_source = _inventory_change_signal(vehicle)
    listing_intensity = _listing_intensity(vehicle)
    market_activity = _bounded(vehicle.market_activity_score)
    price_pressure = _price_pressure(vehicle, inventory_change, inventory_source)
    inventory_pressure = _inventory_pressure(
        inventory_level_score,
        inventory_change,
        listing_intensity,
        market_activity,
        inventory_source,
    )
    momentum = _market_momentum(
        vehicle,
        inventory_change,
        listing_intensity,
        market_activity,
        inventory_source,
    )
    return VehicleQuantitativeScores(
        vehicle_key=vehicle.vehicle_key,
        price_pressure=price_pressure,
        inventory_pressure=inventory_pressure,
        market_momentum=momentum,
    )


def _price_pressure(
    vehicle: VehicleQuantitativeInput,
    inventory_change: float | None,
    inventory_source: str,
) -> QuantitativeIndex:
    components = {
        "price_decline_7d": _decline_pressure(vehicle.price_change_7d_pct, 10),
        "price_decline_30d": _decline_pressure(vehicle.price_change_30d_pct, 15),
        "inventory_growth": _positive_change_pressure(inventory_change),
        "price_dispersion": _price_dispersion(vehicle),
    }
    missing = tuple(name for name, value in components.items() if value is None)
    available_count = sum(value is not None for value in components.values())
    required_available = (
        components["price_decline_7d"] is not None and available_count >= 3
    )
    return _index(
        components,
        PRICE_PRESSURE_WEIGHTS,
        required_available=required_available,
        missing_inputs=missing,
        component_sources={
            "price_decline_7d": "analytics.price_change_7d_pct",
            "price_decline_30d": "analytics.price_change_30d_pct",
            "inventory_growth": inventory_source,
            "price_dispersion": "analytics.current_price_range",
        },
    )


def _inventory_pressure(
    inventory_level: float,
    inventory_change: float | None,
    listing_intensity: float | None,
    market_activity: float | None,
    inventory_source: str,
) -> QuantitativeIndex:
    components = {
        "inventory_level": inventory_level,
        "inventory_growth": _positive_change_pressure(inventory_change),
        "new_listing_intensity": listing_intensity,
        "low_market_activity": (
            100 - market_activity if market_activity is not None else None
        ),
    }
    missing = tuple(name for name, value in components.items() if value is None)
    return _index(
        components,
        INVENTORY_PRESSURE_WEIGHTS,
        required_available=not missing,
        missing_inputs=missing,
        component_sources={
            "inventory_level": "daily_report_peer_min_max",
            "inventory_growth": inventory_source,
            "new_listing_intensity": (
                "analytics.new_listings_count_7d/current_inventory"
            ),
            "low_market_activity": "100-opportunity.market_activity",
        },
    )


def _market_momentum(
    vehicle: VehicleQuantitativeInput,
    inventory_change: float | None,
    listing_intensity: float | None,
    market_activity: float | None,
    inventory_source: str,
) -> MomentumIndex:
    components = {
        "new_listing_activity": listing_intensity,
        "price_opportunity_trend": _price_opportunity_trend(vehicle),
        "inventory_availability_trend": (
            _clamp(50 + 0.5 * inventory_change)
            if inventory_change is not None
            else None
        ),
        "opportunity_score": _bounded(vehicle.opportunity_score),
        "market_activity": market_activity,
    }
    missing = tuple(name for name, value in components.items() if value is None)
    required = (
        "new_listing_activity",
        "inventory_availability_trend",
        "opportunity_score",
        "market_activity",
    )
    result = _index(
        components,
        MARKET_MOMENTUM_WEIGHTS,
        required_available=all(components[name] is not None for name in required),
        missing_inputs=missing,
        component_sources={
            "new_listing_activity": "analytics.new_listings_count_7d/current_inventory",
            "price_opportunity_trend": "analytics.price_change_7d_pct/30d_pct",
            "inventory_availability_trend": inventory_source,
            "opportunity_score": "analytics.opportunity_score",
            "market_activity": "analytics.opportunity_score.market_activity",
        },
    )
    return MomentumIndex(
        score=result.score,
        status=result.status,
        components=result.components,
        weights=result.weights,
        applied_weights=result.applied_weights,
        missing_inputs=result.missing_inputs,
        component_sources=result.component_sources,
        label=(
            classify_market_momentum(result.score) if result.score is not None else None
        ),
    )


def _index(
    components: dict[str, float | None],
    weights: dict[str, float],
    *,
    required_available: bool,
    missing_inputs: tuple[str, ...],
    component_sources: dict[str, str],
) -> QuantitativeIndex:
    if not required_available:
        return QuantitativeIndex(
            score=None,
            status="insufficient_data",
            components=components,
            weights=dict(weights),
            applied_weights={},
            missing_inputs=missing_inputs,
            component_sources=component_sources,
        )
    available_weight = sum(
        weights[name] for name, value in components.items() if value is not None
    )
    applied = {
        name: weight / available_weight
        for name, weight in weights.items()
        if components[name] is not None
    }
    score = sum(
        components[name] * applied[name]
        for name in applied
        if components[name] is not None
    )
    return QuantitativeIndex(
        score=_round(_clamp(score), 2),
        status="available",
        components={
            name: _round(value, 2) if value is not None else None
            for name, value in components.items()
        },
        weights=dict(weights),
        applied_weights={name: _round(value, 4) for name, value in applied.items()},
        missing_inputs=missing_inputs,
        component_sources=component_sources,
    )


def _validate_vehicle_keys(vehicles: tuple[VehicleQuantitativeInput, ...]) -> None:
    keys = [vehicle.vehicle_key for vehicle in vehicles]
    if any(not key.strip() for key in keys):
        raise ValueError("vehicle_key must be non-empty")
    if len(keys) != len(set(keys)):
        raise ValueError("vehicle_key values must be unique")
    for vehicle in vehicles:
        if vehicle.active_listing_count < 0 or vehicle.new_listings_count_7d < 0:
            raise ValueError("listing counts must be non-negative")


def _min_max_inventory_scores(
    vehicles: tuple[VehicleQuantitativeInput, ...],
) -> dict[str, float]:
    if not vehicles:
        return {}
    values = [vehicle.active_listing_count for vehicle in vehicles]
    lower = min(values)
    upper = max(values)
    if lower == upper:
        return {vehicle.vehicle_key: 50.0 for vehicle in vehicles}
    width = upper - lower
    return {
        vehicle.vehicle_key: (vehicle.active_listing_count - lower) / width * 100
        for vehicle in vehicles
    }


def _inventory_change_signal(
    vehicle: VehicleQuantitativeInput,
) -> tuple[float | None, str]:
    reported = _finite(vehicle.inventory_change_7d_pct)
    if reported is not None:
        return reported, "analytics.inventory_change_7d_pct"
    if vehicle.active_listing_count > 0:
        return (
            vehicle.inventory_change_7d_count / vehicle.active_listing_count * 100,
            "analytics.inventory_change_7d_count/current_inventory",
        )
    if vehicle.inventory_change_7d_count == 0:
        return 0.0, "analytics.zero_inventory_change"
    return None, "insufficient_data"


def _listing_intensity(vehicle: VehicleQuantitativeInput) -> float | None:
    if vehicle.active_listing_count > 0:
        return _clamp(
            vehicle.new_listings_count_7d / vehicle.active_listing_count * 100
        )
    if vehicle.new_listings_count_7d == 0:
        return 0.0
    return None


def _decline_pressure(value: float | None, scale_pct: float) -> float | None:
    numeric = _finite(value)
    return None if numeric is None else _clamp(-numeric / scale_pct * 100)


def _positive_change_pressure(value: float | None) -> float | None:
    return None if value is None else _clamp(max(value, 0) / 25 * 100)


def _price_dispersion(vehicle: VehicleQuantitativeInput) -> float | None:
    average = _finite(vehicle.average_price_eur)
    minimum = _finite(vehicle.minimum_price_eur)
    maximum = _finite(vehicle.maximum_price_eur)
    if average is None or minimum is None or maximum is None or average <= 0:
        return None
    if minimum < 0 or maximum < minimum:
        return None
    return _clamp((maximum - minimum) / average * 100)


def _price_opportunity_trend(vehicle: VehicleQuantitativeInput) -> float | None:
    score_7d = _trend_score(vehicle.price_change_7d_pct)
    score_30d = _trend_score(vehicle.price_change_30d_pct)
    if score_7d is not None and score_30d is not None:
        return 0.7 * score_7d + 0.3 * score_30d
    return score_7d if score_7d is not None else score_30d


def _trend_score(value: float | None) -> float | None:
    numeric = _finite(value)
    return None if numeric is None else _clamp(50 - 5 * numeric)


def _bounded(value: float | None) -> float | None:
    numeric = _finite(value)
    return None if numeric is None else _clamp(numeric)


def _finite(value: float | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def _round(value: float, places: int) -> float:
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))
