from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.volkswagen import VolkswagenOfficialPriceBatchImportService
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
    VariantRepository,
    VehicleRepository,
)

COLLECTED_AT = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)
OBSERVED_AT = "2026-07-18T08:00:00+00:00"
SOURCE_URL = "https://www.volkswagen.de/de/modelle/golf.html"


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


def test_official_price_batch_import_imports_multiple_csv_files(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_07.csv", valid_date="2026-07-18"
    )
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_08.csv", valid_date="2026-08-01"
    )

    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)

    result = VolkswagenOfficialPriceBatchImportService(db_sessions).import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    with session_scope(db_sessions) as session:
        assert result.file_count == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.total == 2
        assert result.matched == 2
        assert result.inserted == 2
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 0
        assert BaseRepository(session, OfficialPriceObservation).count() == 2


def test_official_price_batch_import_orders_files_by_file_date(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_08.csv", valid_date="2026-08-01"
    )
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_06.csv", valid_date="2026-06-01"
    )
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_07.csv", valid_date="2026-07-18"
    )

    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)

    result = VolkswagenOfficialPriceBatchImportService(db_sessions).import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    assert [file_result.file_path.name for file_result in result.file_results] == [
        "volkswagen_prices_2026_06.csv",
        "volkswagen_prices_2026_07.csv",
        "volkswagen_prices_2026_08.csv",
    ]
    assert result.inserted == 3


def test_official_price_batch_import_repeat_run_is_idempotent(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_07.csv", valid_date="2026-07-18"
    )
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_08.csv", valid_date="2026-08-01"
    )

    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)

    service = VolkswagenOfficialPriceBatchImportService(db_sessions)
    first = service.import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )
    second = service.import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    with session_scope(db_sessions) as session:
        assert first.inserted == 2
        assert first.updated == 0
        assert first.skipped == 0
        assert second.inserted == 0
        assert second.updated == 0
        assert second.skipped == 2
        assert second.matched == 2
        assert BaseRepository(session, OfficialPriceObservation).count() == 2
        assert BaseRepository(session, Brand).count() == 1
        assert BaseRepository(session, Vehicle).count() == 1


def test_official_price_batch_import_single_file_failure_does_not_stop_later_files(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_07.csv", valid_date="2026-07-18"
    )
    (tmp_path / "volkswagen_prices_2026_08.csv").write_text(
        "canonical_brand_name,canonical_model_name\nVolkswagen,Golf\n",
        encoding="utf-8",
    )
    _write_price_csv(
        tmp_path / "volkswagen_prices_2026_09.csv", valid_date="2026-09-01"
    )

    with session_scope(db_sessions) as session:
        _seed_official_price_master_data(session)

    result = VolkswagenOfficialPriceBatchImportService(db_sessions).import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    with session_scope(db_sessions) as session:
        file_results = {item.file_path.name: item for item in result.file_results}
        assert result.file_count == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert result.total == 2
        assert result.matched == 2
        assert result.inserted == 2
        assert file_results["volkswagen_prices_2026_07.csv"].succeeded is True
        assert file_results["volkswagen_prices_2026_08.csv"].succeeded is False
        assert file_results["volkswagen_prices_2026_08.csv"].error is not None
        assert file_results["volkswagen_prices_2026_09.csv"].succeeded is True
        assert BaseRepository(session, OfficialPriceObservation).count() == 2


def _write_price_csv(
    path: Path,
    *,
    valid_date: str,
    price: str = "29995.00",
) -> None:
    path.write_text(
        "\n".join(
            [
                (
                    "source_url,raw_brand_name,raw_model_name,raw_variant_name,"
                    "canonical_brand_name,canonical_model_name,price_type,"
                    "original_price,original_currency,price_eur,raw_price_text,"
                    "observed_at,valid_date,collected_at,price_includes_vat"
                ),
                (
                    f"{SOURCE_URL},Volkswagen,Golf,Life,Volkswagen,Golf,"
                    f"official_starting_price,{price},EUR,{price},"
                    f"ab {price} EUR,{OBSERVED_AT},{valid_date},"
                    f"{COLLECTED_AT.isoformat()},true"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


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
            notes="Test Volkswagen official price batch source.",
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
