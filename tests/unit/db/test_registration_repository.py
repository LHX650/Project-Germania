from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.kba.models import RegistrationRecord
from germania.db import (
    Base,
    Brand,
    DataSource,
    RegistrationObservation,
    Vehicle,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import (
    BaseRepository,
    BrandRepository,
    DataSourceRepository,
    RegistrationObservationRepository,
    VehicleRepository,
)

COLLECTED_AT = datetime(2026, 7, 18, 9, 15, tzinfo=UTC)


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


def test_registration_observation_saves_kba_fields(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, brand, vehicle = _seed_kba_vehicle(session)
        repository = BaseRepository(session, RegistrationObservation)
        observation = repository.add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="battery_electric",
                market_share=Decimal("0.4000"),
            )
        )

        assert observation.brand_id == brand.brand_id
        assert observation.fuel_type == "battery_electric"
        assert observation.market_share == Decimal("0.4000")


def test_registration_observation_accepts_null_market_share(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, brand, vehicle = _seed_kba_vehicle(session)
        observation = BaseRepository(session, RegistrationObservation).add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="total",
                market_share=None,
            )
        )

        assert observation.market_share is None


def test_registration_observation_unique_key_prevents_same_fuel_duplicate(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, brand, vehicle = _seed_kba_vehicle(session)
        BaseRepository(session, RegistrationObservation).add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="total",
                market_share=None,
            )
        )

    with pytest.raises(IntegrityError), session_scope(db_sessions) as session:
        source = DataSourceRepository(session).get_by_source_id("kba")
        brand = BrandRepository(session).get_by_name("Volkswagen")
        assert source is not None
        assert brand is not None
        vehicle = VehicleRepository(session).get_by_code(brand.brand_id, "Golf")
        assert vehicle is not None
        BaseRepository(session, RegistrationObservation).add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="total",
                market_share=Decimal("4.5000"),
            )
        )


def test_registration_observation_allows_different_fuel_types(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, brand, vehicle = _seed_kba_vehicle(session)
        repository = BaseRepository(session, RegistrationObservation)
        repository.add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="total",
                market_share=None,
            )
        )
        repository.add(
            _registration_observation(
                data_source_id=source.data_source_id,
                brand_id=brand.brand_id,
                vehicle_id=vehicle.vehicle_id,
                fuel_type="battery_electric",
                market_share=Decimal("0.4000"),
            )
        )

        assert repository.count() == 2


def test_registration_repository_upserts_kba_record_idempotently(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _, brand, vehicle = _seed_kba_vehicle(session)
        repository = RegistrationObservationRepository(session)
        record = _kba_record(registrations=1234, market_share=Decimal("4.5"))

        first_result = repository.upsert_kba_record(
            record,
            brand_id=brand.brand_id,
            vehicle_id=vehicle.vehicle_id,
        )
        second_result = repository.upsert_kba_record(
            record,
            brand_id=brand.brand_id,
            vehicle_id=vehicle.vehicle_id,
        )
        updated_result = repository.upsert_kba_record(
            replace(record, registrations=1300),
            brand_id=brand.brand_id,
            vehicle_id=vehicle.vehicle_id,
        )

        observation = repository.get_by_kba_key(
            observation_period="2026-06",
            brand_id=brand.brand_id,
            vehicle_id=vehicle.vehicle_id,
            fuel_type="total",
            source_id="kba",
        )

        assert first_result.created is True
        assert second_result.unchanged is True
        assert updated_result.updated is True
        assert repository.count() == 1
        assert observation is not None
        assert observation.registration_count == 1300
        assert observation.fuel_type == "total"
        assert observation.market_share == Decimal("4.5000")
        assert observation.registration_scope == "Germany"


def _seed_kba_vehicle(session: Session) -> tuple[DataSource, Brand, Vehicle]:
    source = DataSourceRepository(session).add(
        DataSource(
            source_id="kba",
            source_name="Kraftfahrt-Bundesamt (KBA)",
            source_type="government",
            country_code="DE",
            base_url="https://www.kba.de",
            update_frequency="monthly",
            authority_level="primary_authoritative",
            active=True,
            collection_method="manual_download",
            notes="Test KBA source.",
        )
    )
    brand = BrandRepository(session).add(
        Brand(
            canonical_brand="Volkswagen",
            chinese_brand=None,
            manufacturer="Volkswagen AG",
            country_of_origin="Germany",
            active=True,
        )
    )
    vehicle = VehicleRepository(session).add(
        Vehicle(
            brand_id=brand.brand_id,
            canonical_model="Golf",
            chinese_model=None,
            vehicle_segment="compact_car",
            body_type="hatchback",
            default_powertrain="multi_powertrain",
            priority_level="high",
            active=True,
        )
    )
    return source, brand, vehicle


def _registration_observation(
    *,
    data_source_id: int,
    brand_id: int,
    vehicle_id: int,
    fuel_type: str,
    market_share: Decimal | None,
) -> RegistrationObservation:
    return RegistrationObservation(
        data_source_id=data_source_id,
        brand_id=brand_id,
        vehicle_id=vehicle_id,
        vehicle_variant_id=None,
        canonical_brand="Volkswagen",
        canonical_model="Golf",
        raw_brand="Volkswagen",
        raw_model="Golf",
        registration_count=1234,
        fuel_type=fuel_type,
        market_share=market_share,
        sales_value=None,
        sales_metric_type="new_registration",
        registration_period="2026-06",
        registration_scope="Germany",
        region="Germany",
        country_code="DE",
        state=None,
        valid_date=None,
        observed_at=None,
        collected_at=COLLECTED_AT,
        source_url="https://www.kba.de/fz10-test.xlsx",
        source_record_id=None,
        source_file_name=None,
        source_page_number=None,
        data_quality_status="valid",
        validation_status="passed",
        notes=None,
    )


def _kba_record(
    *,
    registrations: int,
    market_share: Decimal | None,
) -> RegistrationRecord:
    return RegistrationRecord(
        source_id="kba",
        year=2026,
        month=6,
        brand="Volkswagen",
        model_series="Golf",
        registrations=registrations,
        fuel_type="total",
        market_share=market_share,
        source_url="https://www.kba.de/fz10-test.xlsx",
        collected_at=COLLECTED_AT,
    )
