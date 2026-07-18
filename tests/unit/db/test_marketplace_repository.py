from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.marketplace import MarketplaceListingRecord
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
    DataSourceRepository,
    MarketplaceListingRepository,
)

COLLECTED_AT = datetime(2026, 7, 19, 8, tzinfo=UTC)


@pytest.fixture()
def db_sessions() -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_marketplace_repository_creates_listing_and_price_history(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        result = MarketplaceListingRepository(session).upsert_listing_record(
            _listing_record(),
        )

        assert result.created is True
        assert result.price_history_created is True
        assert result.listing.external_listing_id == "as24-123"
        assert result.listing.current_price_amount == Decimal("29990.00")
        assert result.listing.currency == "EUR"
        assert result.listing.brand_name == "Volkswagen"
        assert result.listing.model_name == "Golf"
        assert result.listing.seller_city == "Berlin"
        assert result.listing.first_seen_at == COLLECTED_AT
        assert result.listing.last_seen_at == COLLECTED_AT
        assert result.listing.last_collected_at == COLLECTED_AT
        assert result.price_history is not None
        assert result.price_history.price_amount == Decimal("29990.00")
        assert BaseRepository(session, MarketplaceListing).count() == 1
        assert BaseRepository(session, MarketplacePriceHistory).count() == 1


def test_marketplace_unique_constraint_uses_source_and_external_listing_id(
    db_sessions: sessionmaker[Session],
) -> None:
    with pytest.raises(IntegrityError), session_scope(db_sessions) as session:
        source = _seed_marketplace_source(session)
        repository = BaseRepository(session, MarketplaceListing)
        repository.add(
            _listing(
                data_source_id=source.data_source_id,
                external_listing_id="as24-123",
            )
        )
        repository.add(
            _listing(
                data_source_id=source.data_source_id,
                external_listing_id="as24-123",
            )
        )


def test_marketplace_repository_repeated_import_is_idempotent(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        repository = MarketplaceListingRepository(session)
        first_result = repository.upsert_listing_record(_listing_record())
        second_result = repository.upsert_listing_record(_listing_record())

        assert first_result.created is True
        assert second_result.unchanged is True
        assert BaseRepository(session, MarketplaceListing).count() == 1
        assert BaseRepository(session, MarketplacePriceHistory).count() == 1


def test_marketplace_repository_adds_price_history_only_when_price_changes(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        repository = MarketplaceListingRepository(session)
        repository.upsert_listing_record(_listing_record())
        changed = repository.upsert_listing_record(
            replace(
                _listing_record(),
                price_amount=Decimal("28990.00"),
                collected_at=COLLECTED_AT + timedelta(days=1),
            )
        )
        unchanged_price = repository.upsert_listing_record(
            replace(
                _listing_record(),
                mileage_km=12_500,
                price_amount=Decimal("28990.00"),
                collected_at=COLLECTED_AT + timedelta(days=2),
            )
        )

        assert changed.updated is True
        assert changed.price_history_created is True
        assert changed.listing.current_price_amount == Decimal("28990.00")
        assert unchanged_price.updated is True
        assert unchanged_price.price_history_created is False
        assert unchanged_price.listing.mileage_km == 12_500
        assert BaseRepository(session, MarketplacePriceHistory).count() == 2


def test_marketplace_repository_missing_price_does_not_write_history(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        result = MarketplaceListingRepository(session).upsert_listing_record(
            replace(_listing_record(), price_amount=None)
        )

        assert result.created is True
        assert result.price_history is None
        assert result.price_history_created is False
        assert BaseRepository(session, MarketplaceListing).count() == 1
        assert BaseRepository(session, MarketplacePriceHistory).count() == 0


def test_marketplace_repository_unknown_vehicle_does_not_create_master_data(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        result = MarketplaceListingRepository(session).upsert_listing_record(
            replace(_listing_record(), model_name="Unknown Model")
        )

        assert result.created is True
        assert result.listing.vehicle_id is None
        assert result.listing.vehicle_variant_id is None
        assert BaseRepository(session, Brand).count() == 0
        assert BaseRepository(session, Vehicle).count() == 0


def test_marketplace_repository_queries_and_active_status(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        repository = MarketplaceListingRepository(session)
        listing = repository.upsert_listing_record(_listing_record()).listing

        assert (
            repository.get_by_source_listing_key(
                source_id="autoscout24_de",
                external_listing_id="as24-123",
            )
            == listing
        )
        assert repository.list_active(source_id="autoscout24_de") == [listing]

        repository.set_active(
            listing,
            active=False,
            seen_at=COLLECTED_AT + timedelta(days=1),
        )

        assert listing.active is False
        assert repository.list_active(source_id="autoscout24_de") == []


def test_marketplace_repository_rejects_negative_price(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_marketplace_source(session)
        with pytest.raises(ValueError, match="price_amount"):
            MarketplaceListingRepository(session).upsert_listing_record(
                replace(_listing_record(), price_amount=Decimal("-1.00"))
            )


def _seed_marketplace_source(session: Session) -> DataSource:
    return DataSourceRepository(session).add(
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
            notes="Test marketplace source.",
        )
    )


def _listing_record() -> MarketplaceListingRecord:
    return MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id="as24-123",
        listing_url="https://www.autoscout24.de/angebote/as24-123",
        brand_name="Volkswagen",
        model_name="Golf",
        variant_name="Life",
        title="Volkswagen Golf 1.5 eTSI Life",
        price_amount=Decimal("29990.00"),
        currency="EUR",
        registration_year=2024,
        mileage_km=10_000,
        fuel_type="petrol",
        transmission="automatic",
        power_kw=Decimal("110.00"),
        seller_type="dealer",
        seller_name="Berlin Autohaus",
        seller_postcode="10115",
        seller_city="Berlin",
        vehicle_condition="used",
        body_type="hatchback",
        color="blue",
        collected_at=COLLECTED_AT,
        source_updated_at=None,
    )


def _listing(
    *,
    data_source_id: int,
    external_listing_id: str,
) -> MarketplaceListing:
    return MarketplaceListing(
        data_source_id=data_source_id,
        external_listing_id=external_listing_id,
        vehicle_id=None,
        vehicle_variant_id=None,
        brand_name=None,
        model_name=None,
        variant_name=None,
        title=None,
        current_price_amount=Decimal("29990.00"),
        currency="EUR",
        registration_year=None,
        model_year=None,
        first_registration_date=None,
        fuel_type=None,
        transmission=None,
        power_kw=None,
        vehicle_condition=None,
        body_type=None,
        color=None,
        mileage_km=None,
        owner_count=None,
        seller_type=None,
        seller_name=None,
        country_code=None,
        state=None,
        seller_city=None,
        seller_postcode=None,
        listing_url=None,
        first_seen_at=COLLECTED_AT,
        last_seen_at=COLLECTED_AT,
        last_collected_at=COLLECTED_AT,
        source_updated_at=None,
        active=True,
        notes=None,
    )
