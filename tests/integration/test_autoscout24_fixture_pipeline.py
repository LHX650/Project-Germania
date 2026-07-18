from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.autoscout24 import AutoScout24ListingImportService
from germania.db import (
    Base,
    Brand,
    DataSource,
    MarketplaceListing,
    MarketplacePriceHistory,
    Vehicle,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import (
    BaseRepository,
    BrandRepository,
    DataSourceRepository,
    MarketplaceListingRepository,
    VehicleRepository,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "autoscout24"
LISTING_FIXTURE = FIXTURE_DIR / "fixture_pipeline.html"
PRICE_CHANGED_FIXTURE = FIXTURE_DIR / "fixture_pipeline_price_changed.html"
COLLECTED_AT = datetime(2026, 7, 19, 8, tzinfo=UTC)


@pytest.fixture()
def sqlite_sessions(
    tmp_path: Path,
) -> Iterator[sessionmaker[Session]]:
    database_path = tmp_path / "autoscout24_fixture.sqlite3"
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_fixture_pipeline_imports_valid_records_and_rejects_invalid_master_data(
    sqlite_sessions: sessionmaker[Session],
) -> None:
    with session_scope(sqlite_sessions) as session:
        _seed_master_data(session)
        result = AutoScout24ListingImportService(session).import_html(
            LISTING_FIXTURE,
            collected_at=COLLECTED_AT,
        )

        assert result.total == 6
        assert result.inserted == 2
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 4
        assert result.price_history_inserted == 2
        assert BaseRepository(session, MarketplaceListing).count() == 2
        assert BaseRepository(session, MarketplacePriceHistory).count() == 2
        assert BaseRepository(session, Brand).count() == 1
        assert BaseRepository(session, Vehicle).count() == 1
        assert {
            listing.external_listing_id
            for listing in BaseRepository(session, MarketplaceListing).list()
        } == {"as24-golf-101", "as24-golf-102"}

        listing = MarketplaceListingRepository(session).get_by_source_listing_key(
            source_id="autoscout24_de",
            external_listing_id="as24-golf-101",
        )
        assert listing is not None
        assert listing.vehicle_id is not None
        assert listing.brand_name == "Volkswagen"
        assert listing.model_name == "Golf"
        assert listing.current_price_amount == Decimal("24990.00")
        assert listing.registration_year == 2021
        assert listing.mileage_km == 42000
        assert listing.power_kw == Decimal("110.00")
        assert listing.seller_postcode == "10115"
        assert listing.seller_city == "Berlin"
        assert listing.listing_url is not None
        assert "utm_source" not in listing.listing_url
        assert (
            MarketplaceListingRepository(session).get_by_source_listing_key(
                source_id="autoscout24_de",
                external_listing_id="as24-golf-no-price",
            )
            is None
        )
        assert (
            MarketplaceListingRepository(session).get_by_source_listing_key(
                source_id="autoscout24_de",
                external_listing_id="as24-opel-unknown",
            )
            is None
        )
        assert (
            MarketplaceListingRepository(session).get_by_source_listing_key(
                source_id="autoscout24_de",
                external_listing_id="as24-id5-unknown",
            )
            is None
        )


def test_fixture_pipeline_is_idempotent_and_appends_changed_price_history(
    sqlite_sessions: sessionmaker[Session],
) -> None:
    with session_scope(sqlite_sessions) as session:
        _seed_master_data(session)
        service = AutoScout24ListingImportService(session)
        first = service.import_html(LISTING_FIXTURE, collected_at=COLLECTED_AT)
        repeated = service.import_html(LISTING_FIXTURE, collected_at=COLLECTED_AT)
        changed = service.import_html(
            PRICE_CHANGED_FIXTURE,
            collected_at=COLLECTED_AT + timedelta(days=1),
        )

        assert first.inserted == 2
        assert first.price_history_inserted == 2
        assert repeated.inserted == 0
        assert repeated.updated == 0
        assert repeated.skipped == 2
        assert repeated.rejected == 4
        assert repeated.price_history_inserted == 0
        assert changed.total == 1
        assert changed.inserted == 0
        assert changed.updated == 1
        assert changed.skipped == 0
        assert changed.rejected == 0
        assert changed.price_history_inserted == 1
        assert BaseRepository(session, MarketplaceListing).count() == 2
        assert BaseRepository(session, MarketplacePriceHistory).count() == 3

        listing = MarketplaceListingRepository(session).get_by_source_listing_key(
            source_id="autoscout24_de",
            external_listing_id="as24-golf-101",
        )
        assert listing is not None
        assert listing.current_price_amount == Decimal("23490.00")
        assert listing.first_seen_at == COLLECTED_AT.replace(tzinfo=None)
        assert listing.last_seen_at == (COLLECTED_AT + timedelta(days=1)).replace(
            tzinfo=None
        )


def _seed_master_data(session: Session) -> None:
    DataSourceRepository(session).add(
        DataSource(
            source_id="autoscout24_de",
            source_name="AutoScout24 Germany",
            source_type="marketplace",
            country_code="DE",
            base_url="https://www.autoscout24.de",
            update_frequency="daily",
            authority_level="primary_commercial",
            active=True,
            collection_method="html_parse",
            notes="Local fixture source; no network access.",
        )
    )
    brand = BrandRepository(session).add(
        Brand(
            canonical_brand="Volkswagen",
            chinese_brand="大众",
            manufacturer="Volkswagen AG",
            country_of_origin="Germany",
            active=True,
        )
    )
    VehicleRepository(session).add(
        Vehicle(
            brand_id=brand.brand_id,
            canonical_model="Golf",
            chinese_model="高尔夫",
            vehicle_segment="compact_car",
            body_type="hatchback",
            default_powertrain="multi_powertrain",
            priority_level="high",
            active=True,
        )
    )
