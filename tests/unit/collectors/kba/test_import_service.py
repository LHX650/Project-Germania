from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.kba import KBAImportService, RegistrationRecord
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
    VehicleRepository,
)

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "kba"
FZ10_FIXTURE = FIXTURE_DIR / "fz10_2026_06_sample.xlsx"
COLLECTED_AT = datetime(2026, 7, 18, 9, 15, tzinfo=UTC)
SOURCE_URL = "https://www.kba.de/monthly/fz10_2026_06.xlsx"


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


def test_kba_import_service_imports_fixture_xlsx_into_sqlite(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_fixture_master_data(session)
        result = KBAImportService(session).import_xlsx(
            FZ10_FIXTURE,
            source_url=SOURCE_URL,
            collected_at=COLLECTED_AT,
        )
        observations = BaseRepository(session, RegistrationObservation).list()

        assert result.inserted == 5
        assert result.updated == 0
        assert result.skipped == 0
        assert result.total == 5
        assert result.matched == 5
        assert result.rejected == 0
        assert len(observations) == 5
        assert {observation.registration_period for observation in observations} == {
            "2026-06"
        }
        assert {observation.registration_scope for observation in observations} == {
            "Germany"
        }
        assert {observation.fuel_type for observation in observations} == {
            "total",
            "battery_electric",
        }


def test_kba_import_service_preserves_registration_values(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_fixture_master_data(session)
        KBAImportService(session).import_xlsx(
            FZ10_FIXTURE,
            source_url=SOURCE_URL,
            collected_at=COLLECTED_AT,
        )
        observations = BaseRepository(session, RegistrationObservation).list()
        rows = {
            (
                observation.canonical_brand,
                observation.canonical_model,
                observation.fuel_type,
            ): observation
            for observation in observations
        }

        golf_total = rows[("Volkswagen", "Golf", "total")]
        golf_bev = rows[("Volkswagen", "Golf", "battery_electric")]
        enyaq_total = rows[("\u0160koda", "Enyaq", "total")]

        assert golf_total.registration_count == 1234
        assert golf_total.market_share == Decimal("4.5000")
        assert golf_total.source_url == "https://www.kba.de/fz10-test.xlsx"
        assert golf_bev.registration_count == 120
        assert golf_bev.market_share == Decimal("0.4000")
        assert golf_bev.source_url == SOURCE_URL
        assert enyaq_total.registration_count == 77


def test_kba_import_service_second_import_does_not_duplicate(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_fixture_master_data(session)
        first_result = KBAImportService(session).import_xlsx(
            FZ10_FIXTURE,
            source_url=SOURCE_URL,
            collected_at=COLLECTED_AT,
        )

    with session_scope(db_sessions) as session:
        second_result = KBAImportService(session).import_xlsx(
            FZ10_FIXTURE,
            source_url=SOURCE_URL,
            collected_at=COLLECTED_AT,
        )
        count = BaseRepository(session, RegistrationObservation).count()

        assert first_result.inserted == 5
        assert first_result.updated == 0
        assert first_result.skipped == 0
        assert first_result.total == 5
        assert first_result.matched == 5
        assert first_result.rejected == 0
        assert second_result.inserted == 0
        assert second_result.updated == 0
        assert second_result.skipped == 5
        assert second_result.total == 5
        assert second_result.matched == 5
        assert second_result.rejected == 0
        assert count == 5


def test_kba_import_service_applies_approved_brand_mapping(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_source(session)
        _seed_vehicle(session, brand_name="Mercedes-Benz", model_name="EQA")

        result = KBAImportService(session).import_records(
            [
                _registration_record(
                    brand="MERCEDES",
                    model_series="EQA",
                    registrations=42,
                )
            ]
        )
        observations = BaseRepository(session, RegistrationObservation).list()

        assert result.total == 1
        assert result.matched == 1
        assert result.inserted == 1
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 0
        assert observations[0].canonical_brand == "Mercedes-Benz"
        assert observations[0].canonical_model == "EQA"


def test_kba_import_service_maps_nio_el6_and_xpeng_g6(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_source(session)
        _seed_vehicle(session, brand_name="NIO", model_name="EL6")
        _seed_vehicle(session, brand_name="XPENG", model_name="G6")

        result = KBAImportService(session).import_records(
            [
                _registration_record(
                    brand="NIO",
                    model_series="EL6",
                    registrations=12,
                ),
                _registration_record(
                    brand="XPENG",
                    model_series="G6",
                    registrations=34,
                ),
            ]
        )
        rows = {
            (observation.canonical_brand, observation.canonical_model)
            for observation in BaseRepository(session, RegistrationObservation).list()
        }

        assert result.total == 2
        assert result.matched == 2
        assert result.inserted == 2
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 0
        assert rows == {("NIO", "EL6"), ("XPENG", "G6")}


def test_kba_import_service_does_not_apply_rejected_model_mapping(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_kba_source(session)
        _seed_vehicle(session, brand_name="Tesla", model_name="Model Y")

        result = KBAImportService(session).import_records(
            [
                _registration_record(
                    brand="TESLA",
                    model_series="MODEL 3",
                    registrations=99,
                )
            ]
        )

        assert result.total == 1
        assert result.matched == 0
        assert result.inserted == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 1
        assert BaseRepository(session, Vehicle).count() == 1
        assert BaseRepository(session, RegistrationObservation).count() == 0


def _seed_kba_fixture_master_data(session: Session) -> None:
    _seed_kba_source(session)
    _seed_vehicle(session, brand_name="Volkswagen", model_name="Golf")
    _seed_vehicle(session, brand_name="BMW", model_name="iX1")
    _seed_vehicle(session, brand_name="\u0160koda", model_name="Enyaq")


def _seed_kba_source(session: Session) -> None:
    DataSourceRepository(session).add(
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


def _seed_vehicle(
    session: Session,
    *,
    brand_name: str,
    model_name: str,
) -> None:
    brand = BrandRepository(session).add(
        Brand(
            canonical_brand=brand_name,
            chinese_brand=None,
            manufacturer=None,
            country_of_origin=None,
            active=True,
        )
    )
    VehicleRepository(session).add(
        Vehicle(
            brand_id=brand.brand_id,
            canonical_model=model_name,
            chinese_model=None,
            vehicle_segment="test_segment",
            body_type="test_body",
            default_powertrain="unknown",
            priority_level="high",
            active=True,
        )
    )


def _registration_record(
    *,
    brand: str,
    model_series: str,
    registrations: int,
) -> RegistrationRecord:
    return RegistrationRecord(
        source_id="kba",
        year=2026,
        month=6,
        brand=brand,
        model_series=model_series,
        registrations=registrations,
        fuel_type="total",
        market_share=None,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )
