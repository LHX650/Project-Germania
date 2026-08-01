"""Validated, cached, read-only access to Phase 5A intelligence JSON."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from germania.analytics.quantitative_intelligence import (
    VehicleQuantitativeInput,
    VehicleQuantitativeScores,
    calculate_market_quantitative_scores,
)

DEFAULT_REPORT_RELATIVE_PATH = Path("reports/daily_market_intelligence.json")


class IntelligenceReportError(RuntimeError):
    """Raised when the analytics report is missing, unreadable, or invalid."""


@dataclass(frozen=True)
class VehicleMetrics:
    """Vehicle-level metrics emitted by the Phase 5A analytics layer."""

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
    """Transparent opportunity score plus its component values and weights."""

    score: float
    components: dict[str, float | None]
    applied_weights: dict[str, float]


@dataclass(frozen=True)
class VehicleIntelligence:
    """One vehicle record displayed by the intelligence pages."""

    brand: str
    model: str
    metrics: VehicleMetrics
    opportunity_score: OpportunityScore


@dataclass(frozen=True)
class BrandMetrics:
    """Brand-level competition metrics emitted by the analytics layer."""

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
    """One brand record displayed by the competition page."""

    brand: str
    metrics: BrandMetrics


@dataclass(frozen=True)
class DailyMarketIntelligence:
    """Validated daily analytics report used by the read-only Dashboard."""

    report_date: date
    vehicles: tuple[VehicleIntelligence, ...]
    brands: tuple[BrandIntelligence, ...]
    methodology: dict[str, Any]
    quantitative_scores: tuple[VehicleQuantitativeScores, ...]
    source_path: Path

    @property
    def active_inventory_count(self) -> int:
        """Return the active inventory total across all vehicles."""

        return sum(item.metrics.active_listing_count for item in self.vehicles)

    @property
    def new_listings_count_7d(self) -> int:
        """Return the seven-day new-listing total across all vehicles."""

        return sum(item.metrics.new_listings_count_7d for item in self.vehicles)

    @property
    def weighted_average_price_eur(self) -> float | None:
        """Return the listing-count-weighted average asking price."""

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

    @property
    def quantitative_by_vehicle(self) -> dict[str, VehicleQuantitativeScores]:
        """Return current Phase 11 scores keyed by normalized brand and model."""

        return {item.vehicle_key: item for item in self.quantitative_scores}


def get_project_root() -> Path:
    """Return the absolute Project Germania root directory."""

    return Path(__file__).resolve().parents[2]


def resolve_report_path(report_path: str | Path | None = None) -> Path:
    """Resolve the analytics report path without creating it."""

    candidate = (
        Path(report_path).expanduser()
        if report_path is not None
        else DEFAULT_REPORT_RELATIVE_PATH
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return candidate.resolve(strict=False)


def load_daily_market_intelligence(
    report_path: str | Path | None = None,
) -> DailyMarketIntelligence:
    """Load and validate the current report, refreshing when the file changes."""

    path = resolve_report_path(report_path)
    if not path.is_file():
        raise IntelligenceReportError(
            "Phase 5A intelligence report was not found. Generate "
            "reports/daily_market_intelligence.json before opening analytics pages."
        )
    try:
        stat = path.stat()
    except OSError as exc:
        raise IntelligenceReportError(
            "Unable to inspect the Phase 5A intelligence report."
        ) from exc
    return _load_cached(str(path), stat.st_mtime_ns, stat.st_size)


def clear_intelligence_cache() -> None:
    """Clear the in-process report cache, primarily for tests and operations."""

    _load_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_cached(
    path_text: str,
    modified_at_ns: int,
    file_size: int,
) -> DailyMarketIntelligence:
    del modified_at_ns, file_size
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntelligenceReportError(
            "Phase 5A intelligence report is unreadable or is not valid UTF-8 JSON."
        ) from exc
    return _parse_report(payload, source_path=path)


def _parse_report(payload: object, *, source_path: Path) -> DailyMarketIntelligence:
    root = _mapping(payload, "report")
    report_date = _report_date(root.get("date"))
    vehicle_payload = _sequence(root.get("vehicles"), "vehicles")
    brand_payload = _sequence(root.get("brands"), "brands")
    methodology = dict(_mapping(root.get("methodology"), "methodology"))
    vehicles = tuple(_parse_vehicle(item) for item in vehicle_payload)
    return DailyMarketIntelligence(
        report_date=report_date,
        vehicles=vehicles,
        brands=tuple(_parse_brand(item) for item in brand_payload),
        methodology=methodology,
        quantitative_scores=calculate_market_quantitative_scores(
            tuple(_quantitative_input(item) for item in vehicles)
        ),
        source_path=source_path,
    )


def _parse_vehicle(payload: object) -> VehicleIntelligence:
    item = _mapping(payload, "vehicle entry")
    identity = _mapping(item.get("vehicle"), "vehicle")
    metrics = _mapping(item.get("metrics"), "vehicle.metrics")
    opportunity = _mapping(item.get("opportunity_score"), "vehicle.opportunity_score")
    components = _mapping(opportunity.get("components"), "score.components")
    applied_weights = _mapping(
        opportunity.get("applied_weights"), "score.applied_weights"
    )
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
            score=_number(opportunity.get("score"), "opportunity_score.score", 0, 100),
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
                for key, value in applied_weights.items()
            },
        ),
    )


def _parse_brand(payload: object) -> BrandIntelligence:
    item = _mapping(payload, "brand entry")
    metrics = _mapping(item.get("metrics"), "brand.metrics")
    return BrandIntelligence(
        brand=_text(item.get("brand"), "brand"),
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


def _quantitative_input(vehicle: VehicleIntelligence) -> VehicleQuantitativeInput:
    metrics = vehicle.metrics
    return VehicleQuantitativeInput(
        vehicle_key=vehicle_key(vehicle.brand, vehicle.model),
        active_listing_count=metrics.active_listing_count,
        average_price_eur=metrics.average_price_eur,
        minimum_price_eur=metrics.minimum_price_eur,
        maximum_price_eur=metrics.maximum_price_eur,
        price_change_7d_pct=metrics.price_change_7d_pct,
        price_change_30d_pct=metrics.price_change_30d_pct,
        new_listings_count_7d=metrics.new_listings_count_7d,
        inventory_change_7d_count=metrics.inventory_change_7d_count,
        inventory_change_7d_pct=metrics.inventory_change_7d_pct,
        opportunity_score=vehicle.opportunity_score.score,
        market_activity_score=vehicle.opportunity_score.components.get(
            "market_activity"
        ),
    )


def vehicle_key(brand: str, model: str) -> str:
    """Return the stable dynamic key shared by report and quantitative records."""

    return f"{brand.strip()} {model.strip()}"


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IntelligenceReportError(f"{field} must be a JSON object.")
    return value


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise IntelligenceReportError(f"{field} must be a JSON array.")
    return value


def _report_date(value: object) -> date:
    text = _text(value, "date")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise IntelligenceReportError("date must use YYYY-MM-DD format.") from exc


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntelligenceReportError(f"{field} must be non-empty text.")
    return " ".join(value.strip().split())


def _integer(
    value: object,
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntelligenceReportError(f"{field} must be an integer.")
    if minimum is not None and value < minimum:
        raise IntelligenceReportError(f"{field} must be at least {minimum}.")
    return value


def _number(
    value: object,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntelligenceReportError(f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise IntelligenceReportError(f"{field} must be finite.")
    if minimum is not None and result < minimum:
        raise IntelligenceReportError(f"{field} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise IntelligenceReportError(f"{field} must be at most {maximum}.")
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
