"""Strict input models for the Phase 5A daily intelligence JSON."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


class AnalyticsInputError(ValueError):
    """Raised when the Analytics JSON is missing, unreadable, or invalid."""


@dataclass(frozen=True)
class VehicleMetrics:
    """Grounded marketplace metrics for one vehicle."""

    active_listing_count: int
    average_price_eur: float | None
    minimum_price_eur: float | None
    maximum_price_eur: float | None
    price_change_7d_pct: float | None
    price_change_30d_pct: float | None
    new_listings_count_7d: int
    inventory_change_7d_count: int
    inventory_change_7d_pct: float | None


@dataclass(frozen=True)
class OpportunityScore:
    """Project opportunity score and its transparent component values."""

    score: float
    components: dict[str, float | None]
    applied_weights: dict[str, float]


@dataclass(frozen=True)
class VehicleIntelligence:
    """One vehicle observation in the Analytics report."""

    brand: str
    model: str
    metrics: VehicleMetrics
    opportunity_score: OpportunityScore


@dataclass(frozen=True)
class BrandMetrics:
    """Brand competition metrics derived by the Analytics layer."""

    active_inventory_count: int
    active_inventory_rank: int
    average_vehicle_price_eur: float | None
    bev_share_pct: float | None
    phev_share_pct: float | None
    bev_phev_share_pct: float | None
    model_coverage_count: int
    catalog_model_count: int
    model_coverage_pct: float | None


@dataclass(frozen=True)
class BrandIntelligence:
    """One brand observation in the Analytics report."""

    brand: str
    metrics: BrandMetrics


@dataclass(frozen=True)
class DailyMarketIntelligence:
    """Validated, immutable AI input containing only Analytics facts."""

    report_date: date
    vehicles: tuple[VehicleIntelligence, ...]
    brands: tuple[BrandIntelligence, ...]
    methodology: dict[str, Any]
    source_path: Path

    @property
    def active_inventory_count(self) -> int:
        """Return total active listing inventory across tracked vehicles."""

        return sum(item.metrics.active_listing_count for item in self.vehicles)

    @property
    def new_listings_count_7d(self) -> int:
        """Return total seven-day new listings across tracked vehicles."""

        return sum(item.metrics.new_listings_count_7d for item in self.vehicles)

    @property
    def inventory_change_7d_count(self) -> int:
        """Return total seven-day inventory change across tracked vehicles."""

        return sum(item.metrics.inventory_change_7d_count for item in self.vehicles)

    @property
    def weighted_average_price_eur(self) -> float | None:
        """Return listing-weighted mean asking price for priced vehicles."""

        priced = tuple(
            item
            for item in self.vehicles
            if item.metrics.average_price_eur is not None
            and item.metrics.active_listing_count > 0
        )
        denominator = sum(item.metrics.active_listing_count for item in priced)
        if denominator == 0:
            return None
        numerator = sum(
            item.metrics.average_price_eur * item.metrics.active_listing_count
            for item in priced
            if item.metrics.average_price_eur is not None
        )
        return numerator / denominator


def load_analytics_input(path: str | Path) -> DailyMarketIntelligence:
    """Load and strictly validate a Phase 5A daily intelligence JSON file."""

    source_path = Path(path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise AnalyticsInputError(f"Analytics input does not exist: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnalyticsInputError(
            "Analytics input is unreadable or is not valid UTF-8 JSON."
        ) from exc
    return parse_analytics_input(payload, source_path=source_path)


def parse_analytics_input(
    payload: object,
    *,
    source_path: Path = Path("<memory>"),
) -> DailyMarketIntelligence:
    """Validate an already decoded Analytics JSON payload."""

    root = _mapping(payload, "report")
    report_date = _date(root.get("date"), "date")
    vehicle_rows = _sequence(root.get("vehicles"), "vehicles")
    brand_rows = _sequence(root.get("brands"), "brands")
    methodology = dict(_mapping(root.get("methodology"), "methodology"))
    return DailyMarketIntelligence(
        report_date=report_date,
        vehicles=tuple(_vehicle(item) for item in vehicle_rows),
        brands=tuple(_brand(item) for item in brand_rows),
        methodology=methodology,
        source_path=source_path,
    )


def _vehicle(payload: object) -> VehicleIntelligence:
    row = _mapping(payload, "vehicle entry")
    identity = _mapping(row.get("vehicle"), "vehicle")
    metrics = _mapping(row.get("metrics"), "vehicle.metrics")
    score = _mapping(row.get("opportunity_score"), "vehicle.opportunity_score")
    components = _mapping(score.get("components"), "score.components")
    weights = _mapping(score.get("applied_weights"), "score.applied_weights")
    return VehicleIntelligence(
        brand=_text(identity.get("brand"), "vehicle.brand"),
        model=_text(identity.get("model"), "vehicle.model"),
        metrics=VehicleMetrics(
            active_listing_count=_integer(
                metrics.get("active_listing_count"),
                "metrics.active_listing_count",
                minimum=0,
            ),
            average_price_eur=_optional_number(
                metrics.get("average_price_eur"), "metrics.average_price_eur"
            ),
            minimum_price_eur=_optional_number(
                metrics.get("minimum_price_eur"), "metrics.minimum_price_eur"
            ),
            maximum_price_eur=_optional_number(
                metrics.get("maximum_price_eur"), "metrics.maximum_price_eur"
            ),
            price_change_7d_pct=_optional_number(
                metrics.get("price_change_7d_pct"), "metrics.price_change_7d_pct"
            ),
            price_change_30d_pct=_optional_number(
                metrics.get("price_change_30d_pct"), "metrics.price_change_30d_pct"
            ),
            new_listings_count_7d=_integer(
                metrics.get("new_listings_count_7d"),
                "metrics.new_listings_count_7d",
                minimum=0,
            ),
            inventory_change_7d_count=_integer(
                metrics.get("inventory_change_7d_count"),
                "metrics.inventory_change_7d_count",
            ),
            inventory_change_7d_pct=_optional_number(
                metrics.get("inventory_change_7d_pct"),
                "metrics.inventory_change_7d_pct",
            ),
        ),
        opportunity_score=OpportunityScore(
            score=_number(score.get("score"), "opportunity_score.score", 0, 100),
            components={
                _text(key, "component name"): _optional_number(
                    value, f"score.components.{key}", 0, 100
                )
                for key, value in components.items()
            },
            applied_weights={
                _text(key, "weight name"): _number(
                    value, f"score.applied_weights.{key}", 0, 1
                )
                for key, value in weights.items()
            },
        ),
    )


def _brand(payload: object) -> BrandIntelligence:
    row = _mapping(payload, "brand entry")
    metrics = _mapping(row.get("metrics"), "brand.metrics")
    return BrandIntelligence(
        brand=_text(row.get("brand"), "brand"),
        metrics=BrandMetrics(
            active_inventory_count=_integer(
                metrics.get("active_inventory_count"),
                "brand.metrics.active_inventory_count",
                minimum=0,
            ),
            active_inventory_rank=_integer(
                metrics.get("active_inventory_rank"),
                "brand.metrics.active_inventory_rank",
                minimum=1,
            ),
            average_vehicle_price_eur=_optional_number(
                metrics.get("average_vehicle_price_eur"),
                "brand.metrics.average_vehicle_price_eur",
            ),
            bev_share_pct=_optional_number(
                metrics.get("bev_share_pct"), "brand.metrics.bev_share_pct", 0, 100
            ),
            phev_share_pct=_optional_number(
                metrics.get("phev_share_pct"),
                "brand.metrics.phev_share_pct",
                0,
                100,
            ),
            bev_phev_share_pct=_optional_number(
                metrics.get("bev_phev_share_pct"),
                "brand.metrics.bev_phev_share_pct",
                0,
                100,
            ),
            model_coverage_count=_integer(
                metrics.get("model_coverage_count"),
                "brand.metrics.model_coverage_count",
                minimum=0,
            ),
            catalog_model_count=_integer(
                metrics.get("catalog_model_count"),
                "brand.metrics.catalog_model_count",
                minimum=0,
            ),
            model_coverage_pct=_optional_number(
                metrics.get("model_coverage_pct"),
                "brand.metrics.model_coverage_pct",
                0,
                100,
            ),
        ),
    )


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnalyticsInputError(f"{field} must be a JSON object.")
    return value


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise AnalyticsInputError(f"{field} must be a JSON array.")
    return value


def _date(value: object, field: str) -> date:
    text = _text(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise AnalyticsInputError(f"{field} must use YYYY-MM-DD format.") from exc


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalyticsInputError(f"{field} must be non-empty text.")
    return " ".join(value.strip().split())


def _integer(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalyticsInputError(f"{field} must be an integer.")
    if minimum is not None and value < minimum:
        raise AnalyticsInputError(f"{field} must be at least {minimum}.")
    return value


def _number(
    value: object,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticsInputError(f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise AnalyticsInputError(f"{field} must be finite.")
    if minimum is not None and result < minimum:
        raise AnalyticsInputError(f"{field} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise AnalyticsInputError(f"{field} must be at most {maximum}.")
    return result


def _optional_number(
    value: object,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _number(value, field, minimum, maximum)
