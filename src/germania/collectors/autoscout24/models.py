"""Parsed AutoScout24 listing records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from germania.collectors.marketplace import SellerType, VehicleCondition


@dataclass(frozen=True)
class ListingRecord:
    """Normalized raw listing values parsed from AutoScout24 HTML."""

    source_id: str
    listing_id: str | None
    brand: str | None
    model: str | None
    variant: str | None
    price: Decimal | None
    currency: str | None
    registration: str | None
    mileage: int | None
    fuel_type: str | None
    transmission: str | None
    power: str | None
    location: str | None
    url: str | None
    collected_at: datetime
    title: str | None = None
    seller_type: SellerType | None = None
    seller_name: str | None = None
    vehicle_condition: VehicleCondition | None = None
    body_type: str | None = None
    color: str | None = None
