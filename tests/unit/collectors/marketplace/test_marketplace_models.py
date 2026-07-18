from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from germania.collectors.marketplace import MarketplaceListingRecord


def test_marketplace_listing_record_uses_decimal_and_eur_default() -> None:
    record = MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id="as24-123",
        collected_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
        price_amount=Decimal("29990.00"),
    )

    assert record.price_amount == Decimal("29990.00")
    assert isinstance(record.price_amount, Decimal)
    assert record.currency == "EUR"
