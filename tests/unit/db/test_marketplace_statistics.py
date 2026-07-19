from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from germania.collectors.autoscout24 import AutoScout24ListingImportService
from germania.collectors.marketplace import MarketplaceListingRecord
from germania.db import (
    Base,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.marketplace_statistics import (
    get_marketplace_database_summary,
    get_vehicle_marketplace_summary,
)
from germania.db.seed import seed_configuration


def test_marketplace_database_and_vehicle_statistics() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    collected_at = datetime(2026, 7, 19, 8, tzinfo=UTC)

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            result = AutoScout24ListingImportService(session).import_records(
                [
                    _record(
                        "golf-1", "Volkswagen", "Golf", "20000", 10000, collected_at
                    ),
                    _record(
                        "golf-2", "Volkswagen", "Golf", "30000", 30000, collected_at
                    ),
                    _record(
                        "model-y-1", "Tesla", "Model Y", "40000", 20000, collected_at
                    ),
                ]
            )
            assert result.inserted == 3

            summary = get_marketplace_database_summary(session)
            assert summary.marketplace_listings == 3
            assert summary.price_history == 3
            assert [
                (item.brand_name, item.listing_count)
                for item in summary.listings_by_brand
            ] == [
                ("Tesla", 1),
                ("Volkswagen", 2),
            ]
            assert summary.latest_import_time is not None

            vehicle = get_vehicle_marketplace_summary(
                session,
                brand_name="volkswagen",
                model_name="golf",
            )
            assert vehicle.listing_count == 2
            assert vehicle.average_price == Decimal("25000.0")
            assert vehicle.minimum_price == Decimal("20000.00")
            assert vehicle.maximum_price == Decimal("30000.00")
            assert vehicle.average_mileage == Decimal("20000.0")
            assert vehicle.latest_update_time is not None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _record(
    listing_id: str,
    brand: str,
    model: str,
    price: str,
    mileage: int,
    collected_at: datetime,
) -> MarketplaceListingRecord:
    return MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id=listing_id,
        collected_at=collected_at,
        listing_url=f"https://www.autoscout24.de/angebote/{listing_id}",
        brand_name=brand,
        model_name=model,
        price_amount=Decimal(price),
        mileage_km=mileage,
    )
