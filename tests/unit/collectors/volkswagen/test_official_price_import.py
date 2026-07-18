from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.volkswagen import (
    OfficialPriceRecord,
    VolkswagenOfficialPriceImportService,
    VolkswagenOfficialPriceParser,
    parse_official_prices,
)
from germania.db import (
    Base,
    Brand,
    DataSource,
    OfficialPriceObservation,
    Vehicle,
    VehicleVariant,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import (
    BaseRepository,
    BrandRepository,
    DataSourceRepository,
    OfficialPriceRepository,
    VariantRepository,
    VehicleRepository,
)

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "volkswagen"
GOLF_PRICE_FIXTURE = FIXTURE_DIR / "golf_official_prices.html"
COLLECTED_AT = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)
SOURCE_URL = "https://www.volkswagen.de/de/modelle/golf.html"


def test_parser_reads_golf_official_starting_price_fixture() -> None:
    records = parse_official_prices(
        _fixture_text("golf_official_prices.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    record = records[0]
    assert isinstance(record, OfficialPriceRecord)
    assert record.source_id == "volkswagen_de"
    assert record.source_url == SOURCE_URL
    assert record.raw_brand_name == "Volkswagen"
    assert record.raw_model_name == "Golf"
    assert record.raw_variant_name == "Life"
    assert record.canonical_brand_name == "Volkswagen"
    assert record.canonical_model_name == "Golf"
    assert record.price_type == "official_starting_price"
    assert record.original_price == Decimal("29995.00")
    assert isinstance(record.original_price, Decimal)
    assert record.original_currency == "EUR"
    assert record.price_eur == Decimal("29995.00")
    assert record.raw_price_text == "ab 29.995,00 €"
    assert record.valid_date == date(2026, 7, 18)
    assert record.observed_at == datetime(2026, 7, 18, 8, tzinfo=UTC)
    assert record.collected_at == COLLECTED_AT
    assert record.price_includes_vat is True


def test_parser_parses_german_price_format_as_decimal() -> None:
    record = parse_official_prices(
        _official_price_html("29.995,00 €"),
        collected_at=COLLECTED_AT,
    )[0]

    assert record.original_price == Decimal("29995.00")
    assert isinstance(record.price_eur, Decimal)


def test_parser_does_not_treat_monthly_payments_as_official_prices() -> None:
    records = VolkswagenOfficialPriceParser().parse_price_page(
        _fixture_text("golf_official_prices.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    assert {record.price_type for record in records} == {"official_starting_price"}
    assert Decimal("199.00") not in {record.price_eur for record in records}
    assert Decimal("299.00") not in {record.price_eur for record in records}


def test_import_service_rejects_missing_price(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        result = VolkswagenOfficialPriceImportService(session).import_records(
            parse_official_prices(
                _official_price_html("Preis folgt"),
                collected_at=COLLECTED_AT,
            )
        )

        assert result.total == 1
        assert result.inserted == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 1
        assert OfficialPriceRepository(session).count() == 0


def test_import_service_first_import_writes_official_price(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        result = VolkswagenOfficialPriceImportService(session).import_html(
            GOLF_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )
        observations = OfficialPriceRepository(session).list()

        assert result.total == 1
        assert result.inserted == 1
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 0
        assert len(observations) == 1
        observation = observations[0]
        assert observation.official_price == Decimal("29995.00")
        assert observation.currency == "EUR"
        assert observation.valid_date == date(2026, 7, 18)
        assert observation.source_url == SOURCE_URL
        assert observation.raw_brand == "Volkswagen"
        assert observation.raw_model == "Golf"
        assert observation.raw_variant_name == "Life"
        assert observation.data_quality_status == "valid"
        assert observation.validation_status == "passed"
        assert "official_starting_price" in (observation.notes or "")


def test_import_service_second_import_is_idempotent(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        service = VolkswagenOfficialPriceImportService(session)
        first_result = service.import_html(
            GOLF_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )
        second_result = service.import_html(
            GOLF_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )

        assert first_result.inserted == 1
        assert first_result.updated == 0
        assert first_result.skipped == 0
        assert first_result.rejected == 0
        assert second_result.inserted == 0
        assert second_result.updated == 0
        assert second_result.skipped == 1
        assert second_result.rejected == 0
        assert OfficialPriceRepository(session).count() == 1


def test_import_service_unknown_vehicle_does_not_create_master_data(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        result = VolkswagenOfficialPriceImportService(session).import_records(
            parse_official_prices(
                _official_price_html("19.995,00 €", model="Polo"),
                collected_at=COLLECTED_AT,
            )
        )

        assert result.total == 1
        assert result.inserted == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 1
        assert BaseRepository(session, Vehicle).count() == 1
        assert OfficialPriceRepository(session).count() == 0


def test_import_writes_to_official_price_observations_table(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        VolkswagenOfficialPriceImportService(session).import_html(
            GOLF_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )

        assert BaseRepository(session, OfficialPriceObservation).count() == 1


def _fixture_text(filename: str) -> str:
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def _official_price_html(price_text: str, *, model: str = "Golf") -> str:
    return f"""
    <article data-price-card data-price-type="official_starting_price">
      <span data-field="brand">Volkswagen</span>
      <span data-field="model">{model}</span>
      <span data-field="variant">Life</span>
      <span data-field="price">{price_text}</span>
      <span data-field="valid_date">2026-07-18</span>
      <span data-field="observed_at">2026-07-18T08:00:00+00:00</span>
      <span data-field="price_includes_vat">true</span>
    </article>
    """


def _seed_official_price_master_data(session: Session) -> VehicleVariant:
    DataSourceRepository(session).add(
        DataSource(
            source_id="volkswagen_de",
            source_name="Volkswagen Germany",
            source_type="manufacturer",
            country_code="DE",
            base_url="https://www.volkswagen.de",
            update_frequency="irregular",
            authority_level="primary_commercial",
            active=True,
            collection_method="html_parse",
            notes="Test Volkswagen official price source.",
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
    return VariantRepository(session).add(
        VehicleVariant(
            vehicle_id=vehicle.vehicle_id,
            model_year="2026",
            generation=None,
            trim_name="Life",
            variant_name=None,
            edition_name=None,
            drivetrain=None,
            transmission=None,
            powertrain="multi_powertrain",
            fuel_type=None,
            battery_capacity_kwh=None,
            engine_power_kw=None,
            engine_power_ps=None,
            effective_from=None,
            effective_to=None,
            active=True,
        )
    )


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
