"""Read-only marketplace database statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from germania.db.models import MarketplaceListing, MarketplacePriceHistory


@dataclass(frozen=True)
class NamedListingCount:
    """Listing count for one brand."""

    brand_name: str
    listing_count: int


@dataclass(frozen=True)
class VehicleListingCount:
    """Listing count for one canonical brand/model pair."""

    brand_name: str
    model_name: str
    listing_count: int


@dataclass(frozen=True)
class MarketplaceDatabaseSummary:
    """High-level marketplace listing and price-history totals."""

    marketplace_listings: int
    price_history: int
    listings_by_brand: tuple[NamedListingCount, ...]
    listings_by_vehicle: tuple[VehicleListingCount, ...]
    latest_import_time: datetime | None


@dataclass(frozen=True)
class VehicleMarketplaceSummary:
    """Read-only descriptive listing statistics for one vehicle."""

    brand_name: str
    model_name: str
    listing_count: int
    average_price: Decimal | None
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    average_mileage: Decimal | None
    latest_update_time: datetime | None


def get_marketplace_database_summary(
    session: Session,
) -> MarketplaceDatabaseSummary:
    """Return total, grouped, and latest-import marketplace statistics."""

    listing_count = session.scalar(select(func.count()).select_from(MarketplaceListing))
    price_history_count = session.scalar(
        select(func.count()).select_from(MarketplacePriceHistory)
    )
    latest_import_time = session.scalar(
        select(func.max(MarketplaceListing.last_collected_at))
    )

    brand_rows = session.execute(
        select(
            MarketplaceListing.brand_name,
            func.count(MarketplaceListing.marketplace_listing_id),
        )
        .where(MarketplaceListing.brand_name.is_not(None))
        .group_by(MarketplaceListing.brand_name)
        .order_by(MarketplaceListing.brand_name)
    ).all()
    vehicle_rows = session.execute(
        select(
            MarketplaceListing.brand_name,
            MarketplaceListing.model_name,
            func.count(MarketplaceListing.marketplace_listing_id),
        )
        .where(
            MarketplaceListing.brand_name.is_not(None),
            MarketplaceListing.model_name.is_not(None),
        )
        .group_by(MarketplaceListing.brand_name, MarketplaceListing.model_name)
        .order_by(MarketplaceListing.brand_name, MarketplaceListing.model_name)
    ).all()

    return MarketplaceDatabaseSummary(
        marketplace_listings=int(listing_count or 0),
        price_history=int(price_history_count or 0),
        listings_by_brand=tuple(
            NamedListingCount(brand_name=brand_name, listing_count=count)
            for brand_name, count in brand_rows
        ),
        listings_by_vehicle=tuple(
            VehicleListingCount(
                brand_name=brand_name,
                model_name=model_name,
                listing_count=count,
            )
            for brand_name, model_name, count in vehicle_rows
        ),
        latest_import_time=latest_import_time,
    )


def get_vehicle_marketplace_summary(
    session: Session,
    *,
    brand_name: str,
    model_name: str,
) -> VehicleMarketplaceSummary:
    """Return listing price, mileage, and freshness statistics for one vehicle."""

    brand = _required_text(brand_name, "brand_name")
    model = _required_text(model_name, "model_name")
    row = session.execute(
        select(
            func.count(MarketplaceListing.marketplace_listing_id),
            func.avg(MarketplaceListing.current_price_amount),
            func.min(MarketplaceListing.current_price_amount),
            func.max(MarketplaceListing.current_price_amount),
            func.avg(MarketplaceListing.mileage_km),
            func.max(MarketplaceListing.last_collected_at),
        ).where(
            func.lower(MarketplaceListing.brand_name) == brand.casefold(),
            func.lower(MarketplaceListing.model_name) == model.casefold(),
        )
    ).one()

    return VehicleMarketplaceSummary(
        brand_name=brand,
        model_name=model,
        listing_count=int(row[0] or 0),
        average_price=_to_decimal(row[1]),
        minimum_price=_to_decimal(row[2]),
        maximum_price=_to_decimal(row[3]),
        average_mileage=_to_decimal(row[4]),
        latest_update_time=row[5],
    )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return " ".join(value.strip().split())


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
