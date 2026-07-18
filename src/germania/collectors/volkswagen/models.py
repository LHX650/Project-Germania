"""Parsed Volkswagen Germany official price records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from germania.collectors.volkswagen.config import VOLKSWAGEN_DE_SOURCE_ID


@dataclass(frozen=True)
class OfficialPriceRecord:
    """Normalized raw official price values parsed from Volkswagen HTML."""

    source_url: str | None
    raw_brand_name: str | None
    raw_model_name: str | None
    raw_variant_name: str | None
    canonical_brand_name: str | None
    canonical_model_name: str | None
    price_type: str
    original_price: Decimal | None
    original_currency: str | None
    price_eur: Decimal | None
    raw_price_text: str | None
    observed_at: datetime | None
    valid_date: date | None
    collected_at: datetime
    source_id: str = VOLKSWAGEN_DE_SOURCE_ID
    price_includes_vat: bool | None = None
