from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from germania.db import (
    Base,
    Brand,
    DataSource,
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


def test_base_repository_crud_methods(db_sessions: sessionmaker[Session]) -> None:
    with session_scope(db_sessions) as session:
        repository = BaseRepository(session, Brand)
        brand = repository.add(_brand("Volkswagen"))

        assert brand.brand_id is not None
        assert repository.get_by_id(brand.brand_id) == brand
        assert repository.exists(brand.brand_id)
        assert repository.count() == 1
        assert repository.list() == [brand]

        repository.update(brand, {"manufacturer": "Volkswagen AG"}, active=False)
        assert brand.manufacturer == "Volkswagen AG"
        assert brand.active is False

        repository.delete(brand)
        assert repository.get_by_id(brand.brand_id) is None
        assert not repository.exists(brand.brand_id)
        assert repository.count() == 0


def test_base_repository_validates_update_and_pagination(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        repository = BaseRepository(session, Brand)
        brand = repository.add(_brand("Volkswagen"))

        with pytest.raises(ValueError, match="writable column"):
            repository.update(brand, vehicles=[])

        with pytest.raises(ValueError, match="offset"):
            repository.list(offset=-1)

        with pytest.raises(ValueError, match="limit"):
            repository.list(limit=-1)


def test_brand_repository_common_queries(db_sessions: sessionmaker[Session]) -> None:
    with session_scope(db_sessions) as session:
        repository = BrandRepository(session)
        volkswagen = repository.add(_brand("Volkswagen", active=True))
        repository.add(_brand("Inactive Brand", active=False))

        assert repository.get_by_name("Volkswagen") == volkswagen
        assert repository.get_by_name("Missing") is None
        assert repository.list_active() == [volkswagen]


def test_vehicle_repository_common_queries(db_sessions: sessionmaker[Session]) -> None:
    with session_scope(db_sessions) as session:
        brand = BrandRepository(session).add(_brand("Volkswagen"))
        repository = VehicleRepository(session)
        golf = repository.add(_vehicle(brand.brand_id, "Golf", active=True))
        tiguan = repository.add(_vehicle(brand.brand_id, "Tiguan", active=False))

        assert repository.get_by_code(brand.brand_id, "Golf") == golf
        assert repository.get_by_code(brand.brand_id, "Missing") is None
        assert repository.list_by_brand(brand.brand_id) == [golf, tiguan]
        assert repository.list_by_brand(brand.brand_id, active=True) == [golf]
        assert repository.list_active() == [golf]


def test_variant_repository_common_queries(db_sessions: sessionmaker[Session]) -> None:
    with session_scope(db_sessions) as session:
        brand = BrandRepository(session).add(_brand("Volkswagen"))
        vehicle = VehicleRepository(session).add(_vehicle(brand.brand_id, "Golf"))
        repository = VariantRepository(session)
        active_variant = repository.add(
            _variant(vehicle.vehicle_id, "2026", "Life", active=True)
        )
        inactive_variant = repository.add(
            _variant(vehicle.vehicle_id, "2026", "Style", active=False)
        )

        assert repository.list_by_vehicle(vehicle.vehicle_id) == [
            active_variant,
            inactive_variant,
        ]
        assert repository.list_by_vehicle(vehicle.vehicle_id, active=True) == [
            active_variant
        ]


def test_data_source_repository_common_queries(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        repository = DataSourceRepository(session)
        kba = repository.add(_data_source("kba", active=True))
        repository.add(_data_source("legacy_source", active=False))

        assert repository.get_by_source_id("kba") == kba
        assert repository.get_by_source_id("missing") is None
        assert repository.list_active() == [kba]


def test_repository_tests_do_not_leave_database_files(
    db_sessions: sessionmaker[Session],
) -> None:
    bind = db_sessions.kw["bind"]

    assert isinstance(bind, Engine)
    assert bind.url.database == ":memory:"


def _brand(canonical_brand: str, *, active: bool = True) -> Brand:
    return Brand(
        canonical_brand=canonical_brand,
        chinese_brand=None,
        manufacturer=None,
        country_of_origin=None,
        active=active,
    )


def _vehicle(
    brand_id: int,
    canonical_model: str,
    *,
    active: bool = True,
) -> Vehicle:
    return Vehicle(
        brand_id=brand_id,
        canonical_model=canonical_model,
        chinese_model=None,
        vehicle_segment="compact",
        body_type="hatchback",
        default_powertrain="multi_powertrain",
        priority_level="high",
        active=active,
    )


def _variant(
    vehicle_id: int,
    model_year: str,
    trim_name: str,
    *,
    active: bool = True,
) -> VehicleVariant:
    return VehicleVariant(
        vehicle_id=vehicle_id,
        model_year=model_year,
        generation=None,
        trim_name=trim_name,
        variant_name=None,
        edition_name=None,
        drivetrain=None,
        transmission=None,
        powertrain=None,
        fuel_type=None,
        battery_capacity_kwh=None,
        engine_power_kw=None,
        engine_power_ps=None,
        effective_from=None,
        effective_to=None,
        active=active,
    )


def _data_source(source_id: str, *, active: bool = True) -> DataSource:
    return DataSource(
        source_id=source_id,
        source_name=source_id.upper(),
        source_type="government",
        country_code="DE",
        base_url=None,
        update_frequency="monthly",
        authority_level="primary_authoritative",
        active=active,
        collection_method="manual_download",
        notes="Test source",
    )
