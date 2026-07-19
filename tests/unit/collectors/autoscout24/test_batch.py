from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from germania.collectors.autoscout24 import AutoScout24ListingImportService
from germania.collectors.autoscout24.batch import _apply_title_exclusions
from germania.collectors.marketplace import MarketplaceListingRecord
from germania.db import (
    Base,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.seed import seed_configuration


def test_configured_title_exclusion_is_counted_as_rejected() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    collected_at = datetime(2026, 7, 19, 9, tzinfo=UTC)
    records = [
        _record("seal-1", "BYD Seal Excellence", collected_at),
        _record("seal-u-1", "BYD Seal U DM-i Boost", collected_at),
    ]

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            filtered = _apply_title_exclusions(records, ("Seal U", "Seal 6"))
            result = AutoScout24ListingImportService(session).import_records(filtered)

            assert result.total == 2
            assert result.inserted == 1
            assert result.rejected == 1
            assert result.price_history_inserted == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _record(
    listing_id: str,
    title: str,
    collected_at: datetime,
) -> MarketplaceListingRecord:
    return MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id=listing_id,
        collected_at=collected_at,
        listing_url=f"https://www.autoscout24.de/angebote/{listing_id}",
        brand_name="BYD",
        model_name="Seal",
        title=title,
        price_amount=Decimal("39990"),
    )
