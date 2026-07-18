from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.audi import (
    AudiOfficialPriceImportService,
    AudiOfficialPriceParser,
    OfficialPriceRecord,
    parse_audi_official_prices,
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

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "audi"
Q4_ETRON_PRICE_FIXTURE = FIXTURE_DIR / "q4_etron_official_prices.html"
COLLECTED_AT = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)
SOURCE_URL = "https://www.audi.de/de/neuwagen/q4-e-tron/q4-e-tron.html"


def test_parser_reads_q4_etron_official_starting_price_fixture() -> None:
    records = parse_audi_official_prices(
        _fixture_text("q4_etron_official_prices.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    record = records[0]
    assert isinstance(record, OfficialPriceRecord)
    assert record.source_id == "audi_de"
    assert record.source_url == SOURCE_URL
    assert record.raw_brand_name == "Audi"
    assert record.raw_model_name == "Q4 e-tron"
    assert record.raw_variant_name == "Q4 45 e-tron"
    assert record.canonical_brand_name == "Audi"
    assert record.canonical_model_name == "Q4 e-tron"
    assert record.price_type == "official_starting_price"
    assert record.original_price == Decimal("52950.00")
    assert isinstance(record.original_price, Decimal)
    assert record.original_currency == "EUR"
    assert record.price_eur == Decimal("52950.00")
    assert record.raw_price_text == "ab 52.950,00 EUR"
    assert record.valid_date == date(2026, 7, 18)
    assert record.observed_at == datetime(2026, 7, 18, 8, tzinfo=UTC)
    assert record.collected_at == COLLECTED_AT
    assert record.price_includes_vat is True


def test_parser_parses_german_price_format_as_decimal() -> None:
    record = parse_audi_official_prices(
        _official_price_html("52.950,00 EUR"),
        collected_at=COLLECTED_AT,
    )[0]

    assert record.original_price == Decimal("52950.00")
    assert isinstance(record.price_eur, Decimal)


def test_parser_does_not_treat_monthly_payments_as_official_prices() -> None:
    records = AudiOfficialPriceParser().parse_price_page(
        _fixture_text("q4_etron_official_prices.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    assert {record.price_type for record in records} == {"official_starting_price"}
    assert Decimal("429.00") not in {record.price_eur for record in records}
    assert Decimal("529.00") not in {record.price_eur for record in records}


def test_import_service_rejects_missing_price(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        result = AudiOfficialPriceImportService(session).import_records(
            parse_audi_official_prices(
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
        result = AudiOfficialPriceImportService(session).import_html(
            Q4_ETRON_PRICE_FIXTURE,
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
        assert observation.official_price == Decimal("52950.00")
        assert observation.currency == "EUR"
        assert observation.valid_date == date(2026, 7, 18)
        assert observation.source_url == SOURCE_URL
        assert observation.raw_brand == "Audi"
        assert observation.raw_model == "Q4 e-tron"
        assert observation.raw_variant_name == "Q4 45 e-tron"
        assert observation.data_quality_status == "valid"
        assert observation.validation_status == "passed"
        assert "official_starting_price" in (observation.notes or "")


def test_import_service_second_import_is_idempotent(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        service = AudiOfficialPriceImportService(session)
        first_result = service.import_html(
            Q4_ETRON_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )
        second_result = service.import_html(
            Q4_ETRON_PRICE_FIXTURE,
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
        result = AudiOfficialPriceImportService(session).import_records(
            parse_audi_official_prices(
                _official_price_html("59.950,00 EUR", model="Q6 e-tron"),
                collected_at=COLLECTED_AT,
            )
        )

        assert result.total == 1
        assert result.inserted == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 1
        assert BaseRepository(session, Brand).count() == 1
        assert BaseRepository(session, Vehicle).count() == 1
        assert OfficialPriceRepository(session).count() == 0


def test_import_writes_to_official_price_observations_table(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)
        AudiOfficialPriceImportService(session).import_html(
            Q4_ETRON_PRICE_FIXTURE,
            collected_at=COLLECTED_AT,
        )

        assert BaseRepository(session, OfficialPriceObservation).count() == 1


def _fixture_text(filename: str) -> str:
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def _official_price_html(price_text: str, *, model: str = "Q4 e-tron") -> str:
    return f"""
    <article data-price-card data-price-type="official_starting_price">
      <span data-field="brand">Audi</span>
      <span data-field="model">{model}</span>
      <span data-field="variant">Q4 45 e-tron</span>
      <span data-field="price">{price_text}</span>
      <span data-field="valid_date">2026-07-18</span>
      <span data-field="observed_at">2026-07-18T08:00:00+00:00</span>
      <span data-field="price_includes_vat">true</span>
    </article>
    """


def _seed_official_price_master_data(session: Session) -> VehicleVariant:
    DataSourceRepository(session).add(
        DataSource(
            source_id="audi_de",
            source_name="Audi Germany",
            source_type="manufacturer",
            country_code="DE",
            base_url="https://www.audi.de",
            update_frequency="irregular",
            authority_level="primary_commercial",
            active=True,
            collection_method="html_parse",
            notes="Test Audi official price source.",
        )
    )
    brand = BrandRepository(session).add(
        Brand(
            canonical_brand="Audi",
            chinese_brand=None,
            manufacturer="Audi AG",
            country_of_origin="Germany",
            active=True,
        )
    )
    vehicle = VehicleRepository(session).add(
        Vehicle(
            brand_id=brand.brand_id,
            canonical_model="Q4 e-tron",
            chinese_model=None,
            vehicle_segment="compact_electric_suv",
            body_type="suv",
            default_powertrain="battery_electric",
            priority_level="high",
            active=True,
        )
    )
    return VariantRepository(session).add(
        VehicleVariant(
            vehicle_id=vehicle.vehicle_id,
            model_year="2026",
            generation=None,
            trim_name="Q4 45 e-tron",
            variant_name=None,
            edition_name=None,
            drivetrain=None,
            transmission=None,
            powertrain="battery_electric",
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
