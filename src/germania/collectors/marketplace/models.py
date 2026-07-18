"""Common marketplace listing data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

SellerType = Literal["manufacturer", "dealer", "private", "marketplace", "unknown"]
VehicleCondition = Literal["new", "used", "demonstrator", "unknown"]


@dataclass(frozen=True)
class MarketplaceListingRecord:
    """Normalized raw marketplace listing values from a parser or importer."""

    source_id: str
    external_listing_id: str
    collected_at: datetime
    listing_url: str | None = None
    brand_name: str | None = None
    model_name: str | None = None
    variant_name: str | None = None
    title: str | None = None
    price_amount: Decimal | None = None
    currency: str = "EUR"
    registration_year: int | None = None
    mileage_km: int | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    power_kw: Decimal | None = None
    seller_type: SellerType | None = None
    seller_name: str | None = None
    seller_postcode: str | None = None
    seller_city: str | None = None
    vehicle_condition: VehicleCondition | None = None
    body_type: str | None = None
    color: str | None = None
    source_updated_at: datetime | None = None
