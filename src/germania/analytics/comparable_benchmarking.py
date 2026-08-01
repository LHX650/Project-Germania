"""Dynamic comparable-vehicle groups and transparent peer benchmarks."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median


@dataclass(frozen=True)
class ComparableVehicleInput:
    """Validated Analytics and SQLite attributes for one comparable vehicle."""

    vehicle_key: str
    brand: str
    model: str
    average_price_eur: float | None
    vehicle_segment: str | None
    body_type: str | None
    powertrain: str | None
    active_inventory: float | None
    price_change_7d_pct: float | None
    opportunity_score: float | None
    price_pressure: float | None
    inventory_pressure: float | None
    market_momentum: float | None


@dataclass(frozen=True)
class PeerMatchRule:
    """One ordered matching rule used by the staged relaxation process."""

    level: int
    price_tolerance_pct: float
    segment_mode: str
    require_same_powertrain: bool


@dataclass(frozen=True)
class PeerMetricBenchmark:
    """Target value relative to the peer-only median and full-group position."""

    metric: str
    target_value: float | None
    peer_median: float | None
    gap: float | None
    gap_unit: str
    rank: int | None
    percentile: float | None
    available_peer_count: int


@dataclass(frozen=True)
class ComparableVehicleBenchmark:
    """Peer group, method disclosure, metric gaps, and primary peer position."""

    vehicle_key: str
    status: str
    reason: str | None
    peer_keys: tuple[str, ...]
    match_level: int | None
    match_basis: tuple[str, ...]
    sample_size: int
    metrics: dict[str, PeerMetricBenchmark]
    peer_rank: int | None
    peer_percentile: float | None
    advantages: tuple[str, ...]
    disadvantages: tuple[str, ...]


MINIMUM_PEER_COUNT = 2

PEER_MATCH_RULES = (
    PeerMatchRule(1, 20.0, "exact", True),
    PeerMatchRule(2, 35.0, "exact", True),
    PeerMatchRule(3, 20.0, "family", True),
    PeerMatchRule(4, 35.0, "family", True),
    PeerMatchRule(5, 50.0, "family", True),
    PeerMatchRule(6, 35.0, "body", True),
    PeerMatchRule(7, 50.0, "body", True),
    PeerMatchRule(8, 35.0, "family", False),
    PeerMatchRule(9, 50.0, "body", False),
)

PEER_BENCHMARK_METHODOLOGY = {
    "scope": (
        "Dynamic peer comparison using current marketplace asking-price and "
        "active-listing signals. Listing inventory is not sales and asking price "
        "is not transaction price."
    ),
    "minimum_peer_count": MINIMUM_PEER_COUNT,
    "matching_priority": [
        {
            "level": rule.level,
            "price_tolerance_pct": rule.price_tolerance_pct,
            "segment_mode": rule.segment_mode,
            "same_powertrain": rule.require_same_powertrain,
        }
        for rule in PEER_MATCH_RULES
    ],
    "segment_family": (
        "Case-insensitive vehicle_segment tokens after removing only the taxonomy "
        "tokens 'electric', 'battery', and 'ev'. No vehicle names are mapped."
    ),
    "gaps": {
        "price_gap_pct": "(target asking price - peer median) / |peer median| * 100",
        "inventory_gap_pct": (
            "(target active listings - peer median) / |peer median| * 100"
        ),
        "point_gap": "target score or percentage - peer median",
    },
    "primary_rank": (
        "Opportunity Score descending across target plus peers; rank 1 is highest."
    ),
    "percentile": (
        "100 * (group size - descending rank) / (group size - 1); "
        "top rank is 100 and bottom rank is 0."
    ),
    "missing_data": (
        "Missing average price, vehicle segment, or powertrain returns "
        "insufficient_data. A group also requires at least two peers. Metric gaps "
        "remain null when the target or all peer values are missing."
    ),
}

_METRICS = {
    "price_gap_pct": ("average_price_eur", "percent"),
    "inventory_gap_pct": ("active_inventory", "percent"),
    "price_trend_gap_pp": ("price_change_7d_pct", "percentage_points"),
    "opportunity_score_gap": ("opportunity_score", "points"),
    "price_pressure_gap": ("price_pressure", "points"),
    "inventory_pressure_gap": ("inventory_pressure", "points"),
    "market_momentum_gap": ("market_momentum", "points"),
}


def calculate_comparable_vehicle_benchmarks(
    vehicles: tuple[ComparableVehicleInput, ...],
) -> tuple[ComparableVehicleBenchmark, ...]:
    """Build a dynamic peer group and benchmark result for every input vehicle."""

    _validate_inputs(vehicles)
    return tuple(_benchmark_vehicle(target, vehicles) for target in vehicles)


def segment_family(value: str) -> str:
    """Return a transparent taxonomy family without mapping individual vehicles."""

    tokens = tuple(
        token
        for token in re.split(r"[^a-z0-9]+", value.casefold())
        if token and token not in {"electric", "battery", "ev"}
    )
    return "_".join(tokens)


def _benchmark_vehicle(
    target: ComparableVehicleInput,
    vehicles: tuple[ComparableVehicleInput, ...],
) -> ComparableVehicleBenchmark:
    missing = tuple(
        name
        for name, value in (
            ("average_price_eur", target.average_price_eur),
            ("vehicle_segment", target.vehicle_segment),
            ("powertrain", target.powertrain),
        )
        if value is None or (isinstance(value, str) and not value.strip())
    )
    if missing:
        return _insufficient(target.vehicle_key, f"missing: {', '.join(missing)}")

    for rule in PEER_MATCH_RULES:
        peers = tuple(
            candidate
            for candidate in vehicles
            if candidate.vehicle_key != target.vehicle_key
            and _matches(target, candidate, rule)
        )
        if len(peers) >= MINIMUM_PEER_COUNT:
            return _build_result(target, peers, rule)
    return _insufficient(
        target.vehicle_key,
        "fewer than two peers after all declared relaxation levels",
    )


def _matches(
    target: ComparableVehicleInput,
    candidate: ComparableVehicleInput,
    rule: PeerMatchRule,
) -> bool:
    if (
        target.average_price_eur is None
        or target.average_price_eur <= 0
        or candidate.average_price_eur is None
        or candidate.average_price_eur <= 0
        or not candidate.vehicle_segment
        or not candidate.powertrain
    ):
        return False
    price_gap = abs(candidate.average_price_eur - target.average_price_eur)
    if price_gap / target.average_price_eur * 100 > rule.price_tolerance_pct:
        return False
    if rule.require_same_powertrain and not _same_text(
        target.powertrain, candidate.powertrain
    ):
        return False
    if rule.segment_mode == "exact":
        return _same_text(target.vehicle_segment, candidate.vehicle_segment)
    if rule.segment_mode == "family":
        return segment_family(target.vehicle_segment) == segment_family(
            candidate.vehicle_segment
        )
    return bool(target.body_type) and _same_text(target.body_type, candidate.body_type)


def _build_result(
    target: ComparableVehicleInput,
    peers: tuple[ComparableVehicleInput, ...],
    rule: PeerMatchRule,
) -> ComparableVehicleBenchmark:
    metrics = {
        metric: _metric_benchmark(target, peers, metric, field, gap_unit)
        for metric, (field, gap_unit) in _METRICS.items()
    }
    opportunity = metrics["opportunity_score_gap"]
    advantages, disadvantages = _signals(metrics)
    return ComparableVehicleBenchmark(
        vehicle_key=target.vehicle_key,
        status="ok",
        reason=None,
        peer_keys=tuple(peer.vehicle_key for peer in peers),
        match_level=rule.level,
        match_basis=_match_basis(rule),
        sample_size=len(peers),
        metrics=metrics,
        peer_rank=opportunity.rank,
        peer_percentile=opportunity.percentile,
        advantages=advantages,
        disadvantages=disadvantages,
    )


def _metric_benchmark(
    target: ComparableVehicleInput,
    peers: tuple[ComparableVehicleInput, ...],
    metric: str,
    field: str,
    gap_unit: str,
) -> PeerMetricBenchmark:
    target_value = getattr(target, field)
    peer_values = tuple(
        value for peer in peers if (value := getattr(peer, field)) is not None
    )
    peer_median = float(median(peer_values)) if peer_values else None
    gap = _gap(target_value, peer_median, gap_unit)
    rank, percentile = _rank_and_percentile(target_value, peer_values)
    return PeerMetricBenchmark(
        metric=metric,
        target_value=_round_optional(target_value),
        peer_median=_round_optional(peer_median),
        gap=_round_optional(gap),
        gap_unit=gap_unit,
        rank=rank,
        percentile=percentile,
        available_peer_count=len(peer_values),
    )


def _gap(
    target_value: float | None,
    peer_median: float | None,
    gap_unit: str,
) -> float | None:
    if target_value is None or peer_median is None:
        return None
    if gap_unit == "percent":
        return (
            None
            if peer_median == 0
            else (target_value - peer_median) / abs(peer_median) * 100
        )
    return target_value - peer_median


def _rank_and_percentile(
    target_value: float | None,
    peer_values: tuple[float, ...],
) -> tuple[int | None, float | None]:
    if target_value is None or not peer_values:
        return None, None
    group = (target_value, *peer_values)
    rank = 1 + sum(value > target_value for value in group)
    percentile = (
        100.0 if len(group) == 1 else 100 * (len(group) - rank) / (len(group) - 1)
    )
    return rank, _round(percentile)


def _signals(
    metrics: dict[str, PeerMetricBenchmark],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    advantages: list[str] = []
    disadvantages: list[str] = []
    checks = (
        (
            "price_gap_pct",
            -5.0,
            "挂牌均价低于同类中位数",
            "挂牌均价高于同类中位数",
            True,
        ),
        (
            "price_trend_gap_pp",
            1.0,
            "7日价格趋势强于同类中位数",
            "7日价格趋势弱于同类中位数",
            False,
        ),
        (
            "opportunity_score_gap",
            5.0,
            "Opportunity Score 高于同类中位数",
            "Opportunity Score 低于同类中位数",
            False,
        ),
        (
            "price_pressure_gap",
            -5.0,
            "Price Pressure 低于同类中位数",
            "Price Pressure 高于同类中位数",
            True,
        ),
        (
            "inventory_pressure_gap",
            -5.0,
            "Inventory Pressure 低于同类中位数",
            "Inventory Pressure 高于同类中位数",
            True,
        ),
        (
            "market_momentum_gap",
            5.0,
            "Market Momentum 高于同类中位数",
            "Market Momentum 低于同类中位数",
            False,
        ),
    )
    for metric, threshold, advantage, disadvantage, lower_is_better in checks:
        gap = metrics[metric].gap
        if gap is None:
            continue
        if (lower_is_better and gap <= threshold) or (
            not lower_is_better and gap >= threshold
        ):
            advantages.append(advantage)
        opposite = -threshold
        if (lower_is_better and gap >= opposite) or (
            not lower_is_better and gap <= opposite
        ):
            disadvantages.append(disadvantage)
    return tuple(advantages), tuple(disadvantages)


def _match_basis(rule: PeerMatchRule) -> tuple[str, ...]:
    segment_labels = {
        "exact": "exact vehicle_segment",
        "family": "similar segment family",
        "body": "same body_type",
    }
    return (
        f"asking-price distance <= {rule.price_tolerance_pct:.0f}%",
        segment_labels[rule.segment_mode],
        "same powertrain" if rule.require_same_powertrain else "powertrain relaxed",
    )


def _insufficient(vehicle_key: str, reason: str) -> ComparableVehicleBenchmark:
    return ComparableVehicleBenchmark(
        vehicle_key=vehicle_key,
        status="insufficient_data",
        reason=reason,
        peer_keys=(),
        match_level=None,
        match_basis=(),
        sample_size=0,
        metrics={},
        peer_rank=None,
        peer_percentile=None,
        advantages=(),
        disadvantages=(),
    )


def _validate_inputs(vehicles: tuple[ComparableVehicleInput, ...]) -> None:
    keys: set[str] = set()
    for item in vehicles:
        if not item.vehicle_key.strip() or item.vehicle_key in keys:
            raise ValueError("vehicle_key values must be non-empty and unique")
        keys.add(item.vehicle_key)
        for field in (
            "average_price_eur",
            "active_inventory",
            "price_change_7d_pct",
            "opportunity_score",
            "price_pressure",
            "inventory_pressure",
            "market_momentum",
        ):
            value = getattr(item, field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{field} values must be finite numbers or None")
        if item.average_price_eur is not None and item.average_price_eur <= 0:
            raise ValueError("average_price_eur must be positive when present")
        if item.active_inventory is not None and item.active_inventory < 0:
            raise ValueError("active_inventory cannot be negative")


def _same_text(left: str | None, right: str | None) -> bool:
    return bool(left and right) and left.casefold().strip() == right.casefold().strip()


def _round(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _round_optional(value: float | None) -> float | None:
    return None if value is None else _round(value)
