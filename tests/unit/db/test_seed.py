from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from germania.config import load_source_config, load_vehicle_config
from germania.db import (
    Base,
    Brand,
    DataSource,
    DataSourceCategory,
    VehicleAlias,
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
from germania.db.seed import seed_configuration


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


def test_seed_configuration_imports_default_project_yaml(
    db_sessions: sessionmaker[Session],
) -> None:
    vehicle_config = load_vehicle_config()
    source_config = load_source_config()
    expected_brand_count = len(
        {vehicle["canonical_brand"] for vehicle in vehicle_config["vehicles"]}
    )
    expected_category_count = sum(
        len(source["data_categories"]) for source in source_config["sources"]
    )

    with session_scope(db_sessions) as session:
        result = seed_configuration(session)

        assert BrandRepository(session).count() == expected_brand_count
        assert VehicleRepository(session).count() == len(vehicle_config["vehicles"])
        assert DataSourceRepository(session).count() == len(source_config["sources"])
        assert BaseRepository(session, DataSourceCategory).count() == (
            expected_category_count
        )
        assert BaseRepository(session, VehicleAlias).count() >= len(
            vehicle_config["vehicles"]
        )
        assert result.brands.created == expected_brand_count
        assert result.vehicles.created == len(vehicle_config["vehicles"])
        assert result.data_sources.created == len(source_config["sources"])
        assert result.data_source_categories.created == expected_category_count


def test_seed_configuration_is_idempotent(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        first_result = seed_configuration(session)
        first_counts = _database_counts(session)

        second_result = seed_configuration(session)
        second_counts = _database_counts(session)

        assert first_result.created > 0
        assert second_counts == first_counts
        assert second_result.created == 0
        assert second_result.updated == 0
        assert second_result.unchanged > 0


def test_seed_configuration_updates_existing_records_from_yaml(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        brand = BrandRepository(session).add(
            Brand(
                canonical_brand="Volkswagen",
                chinese_brand="stale",
                manufacturer="stale",
                country_of_origin="stale",
                active=False,
            )
        )
        source = DataSourceRepository(session).add(
            DataSource(
                source_id="kba",
                source_name="Stale KBA",
                source_type="government",
                country_code="DE",
                base_url=None,
                update_frequency="monthly",
                authority_level="primary_authoritative",
                active=False,
                collection_method="manual_download",
                notes="stale",
            )
        )

        result = seed_configuration(session)

        assert result.brands.updated >= 1
        assert result.data_sources.updated >= 1
        assert brand.manufacturer == "Volkswagen AG"
        assert brand.country_of_origin == "Germany"
        assert brand.active is True
        assert source.source_name == "Kraftfahrt-Bundesamt (KBA)"
        assert source.base_url == "https://www.kba.de"
        assert source.active is True


def test_seed_configuration_accepts_custom_yaml_paths(
    db_sessions: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    vehicle_path = _write_yaml(tmp_path / "vehicles.yaml", _minimal_vehicle_config())
    source_path = _write_yaml(tmp_path / "sources.yaml", _minimal_source_config())

    with session_scope(db_sessions) as session:
        result = seed_configuration(
            session,
            vehicle_config_path=vehicle_path,
            source_config_path=source_path,
        )
        vehicle = VehicleRepository(session).get_by_code(1, "Example Model")
        source = DataSourceRepository(session).get_by_source_id("example_source")

        assert result.brands.created == 1
        assert result.vehicles.created == 1
        assert result.data_sources.created == 1
        assert result.data_source_categories.created == 1
        assert vehicle is not None
        assert vehicle.default_powertrain == "battery_electric"
        assert source is not None
        assert source.collection_method == "manual_download"


def test_seed_tests_use_sqlite_memory_database(
    db_sessions: sessionmaker[Session],
) -> None:
    bind = db_sessions.kw["bind"]

    assert isinstance(bind, Engine)
    assert bind.url.database == ":memory:"


def _database_counts(session: Session) -> dict[str, int]:
    return {
        "brands": BrandRepository(session).count(),
        "vehicles": VehicleRepository(session).count(),
        "vehicle_aliases": BaseRepository(session, VehicleAlias).count(),
        "data_sources": DataSourceRepository(session).count(),
        "data_source_categories": BaseRepository(session, DataSourceCategory).count(),
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _minimal_vehicle_config() -> dict[str, Any]:
    return {
        "metadata": {"schema_version": 1},
        "vehicles": [
            {
                "canonical_brand": "Example",
                "canonical_model": "Example Model",
                "chinese_brand": "Example CN",
                "chinese_model": "Example Model CN",
                "manufacturer": "Example AG",
                "vehicle_segment": "compact_car",
                "body_type": "hatchback",
                "powertrain": "battery_electric",
                "country_of_origin": "Germany",
                "priority_level": "high",
                "active": True,
                "aliases": {
                    "brand": ["Example"],
                    "model": ["Example Model", "Example EV"],
                },
            }
        ],
    }


def _minimal_source_config() -> dict[str, Any]:
    return {
        "metadata": {"schema_version": 1},
        "sources": [
            {
                "source_id": "example_source",
                "source_name": "Example Source",
                "source_type": "government",
                "country_code": "DE",
                "base_url": "https://example.test",
                "data_categories": ["registrations"],
                "update_frequency": "monthly",
                "authority_level": "primary_authoritative",
                "active": True,
                "collection_method": "manual_download",
                "notes": "Planning-only test source. No network request is made.",
            }
        ],
    }
