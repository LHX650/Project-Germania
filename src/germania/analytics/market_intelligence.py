"""Read-only daily marketplace metrics and transparent opportunity scoring."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import (
    Brand,
    MarketplaceListing,
    MarketplacePriceHistory,
    Vehicle,
)

logger = logging.getLogger(__name__)

NEW_LISTING_WINDOW_DAYS = 7
OPPORTUNITY_WEIGHTS = {
    "inventory_attractiveness": Decimal("0.30"),
    "price_competitiveness": Decimal("0.30"),
    "price_trend": Decimal("0.20"),
    "market_activity": Decimal("0.20"),
}

_BEV_FUEL_TYPES = {
    "battery electric",
    "bev",
    "electric",
    "electricity",
    "elektro",
}
_PHEV_FUEL_TYPES = {
    "elektro/benzin",
    "elektro/diesel",
    "phev",
    "plug-in hybrid",
    "plugin hybrid",
}


@dataclass(frozen=True)
class VehicleMarketMetrics:
    """Daily asking-price and inventory metrics for one canonical vehicle."""

    active_listing_count: int
    average_price_eur: Decimal | None
    minimum_price_eur: Decimal | None
    maximum_price_eur: Decimal | None
    price_change_7d_pct: Decimal | None
    price_change_30d_pct: Decimal | None
    new_listings_count_7d: int
    inventory_change_7d_count: int
    inventory_change_7d_pct: Decimal | None


@dataclass(frozen=True)
class OpportunityScore:
    """Weighted opportunity score and its auditable component values."""

    score: Decimal
    components: dict[str, Decimal | None]
    applied_weights: dict[str, Decimal]


@dataclass(frozen=True)
class VehicleIntelligence:
    """One vehicle entry in the daily market-intelligence report."""

    vehicle: dict[str, str]
    metrics: VehicleMarketMetrics
    opportunity_score: OpportunityScore


@dataclass(frozen=True)
class BrandMarketMetrics:
    """Aggregated active-inventory metrics for one brand."""

    active_inventory_count: int
    active_inventory_rank: int
    average_vehicle_price_eur: Decimal | None
    bev_share_pct: Decimal | None
    phev_share_pct: Decimal | None
    bev_phev_share_pct: Decimal | None
    model_coverage_count: int
    catalog_model_count: int
    model_coverage_pct: Decimal | None


@dataclass(frozen=True)
class BrandIntelligence:
    """One brand entry in the daily market-intelligence report."""

    brand: str
    metrics: BrandMarketMetrics


@dataclass(frozen=True)
class MarketIntelligenceReport:
    """Serializable daily report generated without modifying the database."""

    date: date
    vehicles: tuple[VehicleIntelligence, ...]
    brands: tuple[BrandIntelligence, ...]
    methodology: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible report dictionary."""

        return _json_value(asdict(self))


@dataclass(frozen=True)
class _ListingSnapshot:
    listing_id: int
    brand: str
    model: str
    vehicle_id: int | None
    fuel_type: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    active: bool


@dataclass(frozen=True)
class _VehicleWorkingSet:
    brand: str
    model: str
    current: tuple[_ListingSnapshot, ...]
    prices: tuple[Decimal, ...]
    baseline_7d: tuple[_ListingSnapshot, ...]
    baseline_prices_7d: tuple[Decimal, ...]
    baseline_prices_30d: tuple[Decimal, ...]
    new_listings_7d: int


def build_daily_market_intelligence(
    session: Session,
    *,
    report_date: date,
) -> MarketIntelligenceReport:
    """Calculate a daily report from existing marketplace and catalog records.

    The function is read-only. Asking-price snapshots are reconstructed from
    append-only price history at each cutoff, while active-inventory history is
    inferred from the listing's first/last-seen window and current active flag.
    """

    if not isinstance(report_date, date):
        raise TypeError("report_date must be a date")

    report_end = datetime.combine(report_date + timedelta(days=1), time.min, tzinfo=UTC)
    cutoff_7d = report_end - timedelta(days=NEW_LISTING_WINDOW_DAYS)
    cutoff_30d = report_end - timedelta(days=30)
    listings = _load_listings(session, report_end)
    prices_by_listing = _load_price_histories(session, report_end)
    working_sets = _build_vehicle_working_sets(
        listings,
        prices_by_listing,
        report_end=report_end,
        cutoff_7d=cutoff_7d,
        cutoff_30d=cutoff_30d,
    )
    metrics_by_vehicle = {
        (item.brand, item.model): _calculate_vehicle_metrics(item)
        for item in working_sets
    }
    scores = _calculate_opportunity_scores(metrics_by_vehicle)
    vehicles = tuple(
        VehicleIntelligence(
            vehicle={"brand": brand, "model": model},
            metrics=metrics_by_vehicle[(brand, model)],
            opportunity_score=scores[(brand, model)],
        )
        for brand, model in sorted(metrics_by_vehicle)
    )
    brands = _calculate_brand_metrics(session, working_sets)

    return MarketIntelligenceReport(
        date=report_date,
        vehicles=vehicles,
        brands=brands,
        methodology=_methodology(),
    )


def write_daily_market_intelligence(
    report: MarketIntelligenceReport,
    output_path: Path,
) -> Path:
    """Write a report atomically as UTF-8 JSON and return its resolved path."""

    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = json.dumps(
        report.to_dict(), ensure_ascii=False, indent=2, sort_keys=False
    )
    temporary_path.write_text(f"{payload}\n", encoding="utf-8")
    temporary_path.replace(path)
    logger.info("Wrote daily market-intelligence report to %s", path)
    return path


def _load_listings(
    session: Session,
    report_end: datetime,
) -> tuple[_ListingSnapshot, ...]:
    rows = session.execute(
        select(
            MarketplaceListing.marketplace_listing_id,
            MarketplaceListing.brand_name,
            MarketplaceListing.model_name,
            MarketplaceListing.vehicle_id,
            MarketplaceListing.fuel_type,
            MarketplaceListing.first_seen_at,
            MarketplaceListing.last_seen_at,
            MarketplaceListing.active,
        ).where(
            MarketplaceListing.brand_name.is_not(None),
            MarketplaceListing.model_name.is_not(None),
            MarketplaceListing.first_seen_at < report_end,
        )
    ).all()
    return tuple(
        _ListingSnapshot(
            listing_id=row[0],
            brand=_clean_name(row[1]),
            model=_clean_name(row[2]),
            vehicle_id=row[3],
            fuel_type=row[4],
            first_seen_at=_as_utc(row[5]),
            last_seen_at=_as_utc(row[6]),
            active=bool(row[7]),
        )
        for row in rows
    )


def _load_price_histories(
    session: Session,
    report_end: datetime,
) -> dict[int, tuple[tuple[datetime, Decimal], ...]]:
    rows = session.execute(
        select(
            MarketplacePriceHistory.marketplace_listing_id,
            MarketplacePriceHistory.observed_at,
            MarketplacePriceHistory.price_amount,
        )
        .where(
            MarketplacePriceHistory.observed_at < report_end,
            MarketplacePriceHistory.currency == "EUR",
        )
        .order_by(
            MarketplacePriceHistory.marketplace_listing_id,
            MarketplacePriceHistory.observed_at,
        )
    ).all()
    grouped: dict[int, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for listing_id, observed_at, price in rows:
        grouped[listing_id].append((_as_utc(observed_at), Decimal(price)))
    return {key: tuple(value) for key, value in grouped.items()}


def _build_vehicle_working_sets(
    listings: tuple[_ListingSnapshot, ...],
    prices_by_listing: dict[int, tuple[tuple[datetime, Decimal], ...]],
    *,
    report_end: datetime,
    cutoff_7d: datetime,
    cutoff_30d: datetime,
) -> tuple[_VehicleWorkingSet, ...]:
    grouped: dict[tuple[str, str], list[_ListingSnapshot]] = defaultdict(list)
    for listing in listings:
        grouped[(listing.brand, listing.model)].append(listing)

    results: list[_VehicleWorkingSet] = []
    for (brand, model), vehicle_listings in grouped.items():
        current = tuple(
            item
            for item in vehicle_listings
            if _is_active_at(item, report_end, current_snapshot=True)
        )
        if not current:
            continue
        baseline_7d = tuple(
            item for item in vehicle_listings if _is_active_at(item, cutoff_7d)
        )
        baseline_30d = tuple(
            item for item in vehicle_listings if _is_active_at(item, cutoff_30d)
        )
        results.append(
            _VehicleWorkingSet(
                brand=brand,
                model=model,
                current=current,
                prices=_snapshot_prices(current, prices_by_listing, report_end),
                baseline_7d=baseline_7d,
                baseline_prices_7d=_snapshot_prices(
                    baseline_7d, prices_by_listing, cutoff_7d
                ),
                baseline_prices_30d=_snapshot_prices(
                    baseline_30d, prices_by_listing, cutoff_30d
                ),
                new_listings_7d=sum(
                    1
                    for item in vehicle_listings
                    if item.first_seen_at is not None
                    and cutoff_7d <= item.first_seen_at < report_end
                ),
            )
        )
    return tuple(results)


def _calculate_vehicle_metrics(
    item: _VehicleWorkingSet,
) -> VehicleMarketMetrics:
    active_count = len(item.current)
    baseline_count = len(item.baseline_7d)
    current_average = _average(item.prices)
    average_7d = _average(item.baseline_prices_7d)
    average_30d = _average(item.baseline_prices_30d)
    inventory_change = active_count - baseline_count
    return VehicleMarketMetrics(
        active_listing_count=active_count,
        average_price_eur=_money(current_average),
        minimum_price_eur=_money(min(item.prices)) if item.prices else None,
        maximum_price_eur=_money(max(item.prices)) if item.prices else None,
        price_change_7d_pct=_percentage_change(current_average, average_7d),
        price_change_30d_pct=_percentage_change(current_average, average_30d),
        new_listings_count_7d=item.new_listings_7d,
        inventory_change_7d_count=inventory_change,
        inventory_change_7d_pct=(
            _round_decimal(Decimal(inventory_change) / baseline_count * 100)
            if baseline_count
            else None
        ),
    )


def _calculate_opportunity_scores(
    metrics: dict[tuple[str, str], VehicleMarketMetrics],
) -> dict[tuple[str, str], OpportunityScore]:
    inventory_values = {
        key: Decimal(value.active_listing_count) for key, value in metrics.items()
    }
    price_values = {
        key: value.average_price_eur
        for key, value in metrics.items()
        if value.average_price_eur is not None
    }
    activity_values = {
        key: Decimal(value.new_listings_count_7d)
        / Decimal(max(value.active_listing_count, 1))
        for key, value in metrics.items()
    }
    inventory_scores = _percentile_scores(inventory_values)
    price_scores = _percentile_scores(price_values, reverse=True)
    activity_scores = _percentile_scores(activity_values)

    results: dict[tuple[str, str], OpportunityScore] = {}
    for key, value in metrics.items():
        trend_change = (
            value.price_change_30d_pct
            if value.price_change_30d_pct is not None
            else value.price_change_7d_pct
        )
        components: dict[str, Decimal | None] = {
            "inventory_attractiveness": inventory_scores.get(key),
            "price_competitiveness": price_scores.get(key),
            "price_trend": (
                _clamp(Decimal("50") - Decimal("5") * trend_change)
                if trend_change is not None
                else None
            ),
            "market_activity": activity_scores.get(key),
        }
        available_weight = sum(
            OPPORTUNITY_WEIGHTS[name]
            for name, score in components.items()
            if score is not None
        )
        normalized_weights = {
            name: weight / available_weight
            for name, weight in OPPORTUNITY_WEIGHTS.items()
            if components[name] is not None
        }
        score = sum(
            components[name] * normalized_weights[name]
            for name in normalized_weights
            if components[name] is not None
        )
        results[key] = OpportunityScore(
            score=_round_decimal(_clamp(score)),
            components={
                name: _round_decimal(component) if component is not None else None
                for name, component in components.items()
            },
            applied_weights={
                name: _round_weight(weight)
                for name, weight in normalized_weights.items()
            },
        )
    return results


def _calculate_brand_metrics(
    session: Session,
    working_sets: tuple[_VehicleWorkingSet, ...],
) -> tuple[BrandIntelligence, ...]:
    grouped: dict[str, list[_VehicleWorkingSet]] = defaultdict(list)
    for item in working_sets:
        grouped[item.brand].append(item)
    catalog = _load_brand_catalog(session)
    ranked = sorted(
        grouped,
        key=lambda brand: (-sum(len(item.current) for item in grouped[brand]), brand),
    )
    results: list[BrandIntelligence] = []
    previous_count: int | None = None
    current_rank = 0
    for position, brand in enumerate(ranked, start=1):
        items = grouped[brand]
        listings = tuple(listing for item in items for listing in item.current)
        prices = tuple(price for item in items for price in item.prices)
        inventory_count = len(listings)
        if inventory_count != previous_count:
            current_rank = position
            previous_count = inventory_count
        bev_count = sum(
            1 for listing in listings if _fuel_category(listing.fuel_type) == "bev"
        )
        phev_count = sum(
            1 for listing in listings if _fuel_category(listing.fuel_type) == "phev"
        )
        observed_vehicle_ids = {
            listing.vehicle_id for listing in listings if listing.vehicle_id is not None
        }
        catalog_vehicle_ids = catalog.get(brand.casefold(), set())
        coverage_count = len(observed_vehicle_ids & catalog_vehicle_ids)
        results.append(
            BrandIntelligence(
                brand=brand,
                metrics=BrandMarketMetrics(
                    active_inventory_count=inventory_count,
                    active_inventory_rank=current_rank,
                    average_vehicle_price_eur=_money(_average(prices)),
                    bev_share_pct=_share(bev_count, inventory_count),
                    phev_share_pct=_share(phev_count, inventory_count),
                    bev_phev_share_pct=_share(bev_count + phev_count, inventory_count),
                    model_coverage_count=coverage_count,
                    catalog_model_count=len(catalog_vehicle_ids),
                    model_coverage_pct=_share(coverage_count, len(catalog_vehicle_ids)),
                ),
            )
        )
    return tuple(results)


def _load_brand_catalog(session: Session) -> dict[str, set[int]]:
    rows = session.execute(
        select(Brand.canonical_brand, Vehicle.vehicle_id)
        .join(Vehicle, Vehicle.brand_id == Brand.brand_id)
        .where(Brand.active.is_(True), Vehicle.active.is_(True))
    ).all()
    result: dict[str, set[int]] = defaultdict(set)
    for brand, vehicle_id in rows:
        result[_clean_name(brand).casefold()].add(vehicle_id)
    return dict(result)


def _snapshot_prices(
    listings: tuple[_ListingSnapshot, ...],
    prices_by_listing: dict[int, tuple[tuple[datetime, Decimal], ...]],
    cutoff: datetime,
) -> tuple[Decimal, ...]:
    prices: list[Decimal] = []
    for listing in listings:
        histories = prices_by_listing.get(listing.listing_id, ())
        last_price = next(
            (
                price
                for observed_at, price in reversed(histories)
                if observed_at < cutoff
            ),
            None,
        )
        if last_price is not None:
            prices.append(last_price)
    return tuple(prices)


def _is_active_at(
    listing: _ListingSnapshot,
    cutoff: datetime,
    *,
    current_snapshot: bool = False,
) -> bool:
    if listing.first_seen_at is None or listing.first_seen_at >= cutoff:
        return False
    if current_snapshot:
        return listing.active
    return listing.active or (
        listing.last_seen_at is not None and listing.last_seen_at >= cutoff
    )


def _percentile_scores(
    values: dict[tuple[str, str], Decimal | None],
    *,
    reverse: bool = False,
) -> dict[tuple[str, str], Decimal]:
    concrete = {key: value for key, value in values.items() if value is not None}
    unique = sorted(set(concrete.values()))
    if len(unique) <= 1:
        return {key: Decimal("50") for key in concrete}
    denominator = Decimal(len(unique) - 1)
    scores: dict[tuple[str, str], Decimal] = {}
    for key, value in concrete.items():
        rank = unique.index(value)
        score = Decimal(rank) / denominator * 100
        scores[key] = Decimal("100") - score if reverse else score
    return scores


def _methodology() -> dict[str, Any]:
    return {
        "scope": (
            "Marketplace asking prices and listing inventory; listing counts are not "
            "sales and asking prices are not confirmed transaction prices."
        ),
        "formulas": {
            "active_listing_count": (
                "Count of listings marked active whose first_seen_at is before the "
                "end of the report date."
            ),
            "average_minimum_maximum_price_eur": (
                "Mean/minimum/maximum of the latest EUR asking-price history at the "
                "report cutoff for active listings; listings without a price are "
                "excluded, and non-EUR records are not mixed into EUR metrics."
            ),
            "price_change_Nd_pct": (
                "((current active-listing mean asking price / reconstructed mean "
                "asking price N days earlier) - 1) * 100."
            ),
            "new_listings_count_7d": (
                "Count with cutoff_7d <= first_seen_at < report_end."
            ),
            "inventory_change_7d": (
                "current active count - inferred active count 7 days earlier; percent "
                "change divides that difference by the earlier count."
            ),
            "brand_average_vehicle_price_eur": (
                "Mean latest asking price across active listings for the brand."
            ),
            "bev_phev_share_pct": (
                "BEV or PHEV classified active listings / all active brand "
                "listings * 100."
            ),
            "model_coverage_pct": (
                "Active catalog vehicle IDs represented by active listings / all "
                "active catalog vehicle IDs for the brand * 100."
            ),
            "opportunity_score": (
                "Weighted mean of available 0-100 components. Inventory attractiveness "
                "is the active-count percentile; price competitiveness is the inverse "
                "average-price percentile; price trend is clamp(50 - 5 * price_change, "
                "0, 100), preferring 30d then 7d; market activity is the percentile of "
                "new_listings_count_7d / active_listing_count."
            ),
        },
        "opportunity_score_weights": {
            key: _json_value(value) for key, value in OPPORTUNITY_WEIGHTS.items()
        },
        "missing_data_rules": {
            "prices": (
                "Null price metrics; do not impute or treat missing prices as zero."
            ),
            "historical_baseline": (
                "Null price/inventory percent change when no valid baseline exists."
            ),
            "fuel_type": "Exclude unknown fuel types from BEV/PHEV numerators.",
            "catalog": (
                "Null model coverage percent when the brand has no catalog models."
            ),
            "opportunity_components": (
                "Exclude unavailable components and renormalize remaining weights; "
                "never invent a component value."
            ),
            "empty_database": "Return empty vehicles and brands arrays.",
        },
        "inventory_history_limitation": (
            "Past activity is inferred from first_seen_at, last_seen_at, and the "
            "current active flag because absence from a collection is not proof of "
            "sale or removal."
        ),
    }


def _fuel_category(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().casefold().split())
    if normalized in _BEV_FUEL_TYPES:
        return "bev"
    if normalized in _PHEV_FUEL_TYPES:
        return "phev"
    return None


def _clean_name(value: str) -> str:
    return " ".join(value.strip().split())


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _average(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _percentage_change(
    current: Decimal | None,
    baseline: Decimal | None,
) -> Decimal | None:
    if current is None or baseline in {None, Decimal("0")}:
        return None
    return _round_decimal((current / baseline - 1) * 100)


def _share(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return _round_decimal(Decimal(numerator) / Decimal(denominator) * 100)


def _money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round_weight(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal("100"), max(Decimal("0"), value))


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
