from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.kba import KBABatchImportService
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

COLLECTED_AT = datetime(2026, 7, 18, 9, 15, tzinfo=UTC)
SOURCE_URL = "https://www.kba.de/monthly/fz10_history.xlsx"


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


def test_kba_batch_import_imports_multiple_files(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_kba_workbook(tmp_path / "fz10_2026_05.xlsx", year=2026, month=5, count=100)
    _write_kba_workbook(tmp_path / "fz10_2026_06.xlsx", year=2026, month=6, count=120)

    with session_scope(db_sessions) as session:
        _seed_master_data(session)

    result = KBABatchImportService(db_sessions).import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    with session_scope(db_sessions) as session:
        observations = BaseRepository(session, RegistrationObservation).list()
        assert result.file_count == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.total == 2
        assert result.matched == 2
        assert result.inserted == 2
        assert result.updated == 0
        assert result.skipped == 0
        assert result.rejected == 0
        assert len(observations) == 2
        assert {row.registration_period for row in observations} == {
            "2026-05",
            "2026-06",
        }


def test_kba_batch_import_repeat_run_is_idempotent(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_kba_workbook(tmp_path / "fz10_2026_05.xlsx", year=2026, month=5, count=100)
    _write_kba_workbook(tmp_path / "fz10_2026_06.xlsx", year=2026, month=6, count=120)

    with session_scope(db_sessions) as session:
        _seed_master_data(session)

    service = KBABatchImportService(db_sessions)
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
        assert BaseRepository(session, RegistrationObservation).count() == 2
        assert BaseRepository(session, Brand).count() == 1
        assert BaseRepository(session, Vehicle).count() == 1


def test_kba_batch_import_orders_files_by_file_date(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_kba_workbook(tmp_path / "fz10_2026_06.xlsx", year=2026, month=6, count=120)
    _write_kba_workbook(tmp_path / "fz10_2026_04.xlsx", year=2026, month=4, count=80)
    _write_kba_workbook(tmp_path / "fz10_2026_05.xlsx", year=2026, month=5, count=100)

    with session_scope(db_sessions) as session:
        _seed_master_data(session)

    result = KBABatchImportService(db_sessions).import_directory(
        tmp_path,
        source_url=SOURCE_URL,
        collected_at=COLLECTED_AT,
    )

    assert [file_result.file_path.name for file_result in result.file_results] == [
        "fz10_2026_04.xlsx",
        "fz10_2026_05.xlsx",
        "fz10_2026_06.xlsx",
    ]
    assert result.inserted == 3


def test_kba_batch_import_single_file_failure_does_not_stop_other_files(
    tmp_path: Path,
    db_sessions: sessionmaker[Session],
) -> None:
    _write_kba_workbook(tmp_path / "fz10_2026_05.xlsx", year=2026, month=5, count=100)
    (tmp_path / "fz10_2026_06.xlsx").write_text(
        "not an xlsx workbook", encoding="utf-8"
    )
    _write_kba_workbook(tmp_path / "fz10_2026_07.xlsx", year=2026, month=7, count=140)

    with session_scope(db_sessions) as session:
        _seed_master_data(session)

    result = KBABatchImportService(db_sessions).import_directory(
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
        assert result.inserted == 2
        assert file_results["fz10_2026_05.xlsx"].succeeded is True
        assert file_results["fz10_2026_06.xlsx"].succeeded is False
        assert file_results["fz10_2026_06.xlsx"].error is not None
        assert file_results["fz10_2026_07.xlsx"].succeeded is True
        assert BaseRepository(session, RegistrationObservation).count() == 2


def _write_kba_workbook(
    path: Path,
    *,
    year: int,
    month: int,
    count: int,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = f"{year}-{month:02d}"
    worksheet.append([f"Berichtsmonat: {year}-{month:02d}"])
    worksheet.append(["Hersteller", "Handelsname", "Neuzulassungen"])
    worksheet.append(["Volkswagen", "Golf", count])
    workbook.save(path)


def _seed_master_data(session: Session) -> None:
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
            notes="Test KBA batch source.",
        )
    )
    brand = BrandRepository(session).add(
        Brand(
            canonical_brand="Volkswagen",
            chinese_brand=None,
            manufacturer=None,
            country_of_origin=None,
            active=True,
        )
    )
    VehicleRepository(session).add(
        Vehicle(
            brand_id=brand.brand_id,
            canonical_model="Golf",
            chinese_model=None,
            vehicle_segment="test_segment",
            body_type="test_body",
            default_powertrain="unknown",
            priority_level="high",
            active=True,
        )
    )
