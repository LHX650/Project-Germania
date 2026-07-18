from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Numeric,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import configure_mappers

from germania.db import (
    Base,
    Brand,
    CollectionBatch,
    DataQualityIssue,
    DataSource,
    DataSourceCategory,
    EstimatedTransactionPrice,
    ExchangeRateObservation,
    MarketplaceListing,
    MarketplaceListingObservation,
    MarketplacePriceHistory,
    OfficialPriceObservation,
    RegistrationObservation,
    Vehicle,
    VehicleAlias,
    VehicleVariant,
)

EXPECTED_TABLES = {
    "data_sources",
    "data_source_categories",
    "brands",
    "vehicles",
    "vehicle_aliases",
    "vehicle_variants",
    "collection_batches",
    "official_price_observations",
    "marketplace_listings",
    "marketplace_listing_observations",
    "marketplace_price_history",
    "registration_observations",
    "exchange_rate_observations",
    "estimated_transaction_prices",
    "data_quality_issues",
}


def test_base_metadata_contains_expected_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert len(Base.metadata.tables) == 15


def test_table_names_are_unique_and_match_design() -> None:
    table_names = [table.name for table in Base.metadata.tables.values()]

    assert len(table_names) == len(set(table_names))
    assert set(table_names) == EXPECTED_TABLES


def test_each_table_has_primary_key() -> None:
    for table in Base.metadata.tables.values():
        assert len(table.primary_key.columns) >= 1, table.name


def test_foreign_key_target_tables_exist() -> None:
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.name in EXPECTED_TABLES


def test_required_unique_constraints_exist() -> None:
    assert ("source_id",) in _unique_columns(DataSource.__table__)
    assert ("canonical_brand",) in _unique_columns(Brand.__table__)
    assert ("brand_id", "canonical_model") in _unique_columns(Vehicle.__table__)
    assert ("normalized_alias",) in _unique_columns(VehicleAlias.__table__)
    assert ("data_source_id", "external_listing_id") in _unique_columns(
        MarketplaceListing.__table__
    )
    assert ("marketplace_listing_id", "observed_at") in _unique_columns(
        MarketplaceListingObservation.__table__
    )
    assert ("marketplace_listing_id", "observed_at") in _unique_columns(
        MarketplacePriceHistory.__table__
    )
    assert (
        "data_source_id",
        "brand_id",
        "vehicle_id",
        "registration_period",
        "fuel_type",
    ) in _unique_columns(RegistrationObservation.__table__)
    assert (
        "data_source_id",
        "base_currency",
        "quote_currency",
        "exchange_rate_date",
    ) in _unique_columns(ExchangeRateObservation.__table__)
    assert ("batch_id",) in _unique_columns(CollectionBatch.__table__)
    assert ("data_source_id", "data_category") in _unique_columns(
        DataSourceCategory.__table__
    )


def test_key_check_constraints_exist() -> None:
    assert _has_check(DataSource.__table__, "source_type_allowed")
    assert _has_check(Vehicle.__table__, "priority_level_allowed")
    assert _has_check(VehicleAlias.__table__, "alias_type_allowed")
    assert _has_check(VehicleVariant.__table__, "battery_capacity_kwh_non_negative")
    assert _has_check(CollectionBatch.__table__, "batch_counts_consistent")
    assert _has_check(OfficialPriceObservation.__table__, "official_price_non_negative")
    assert _has_check(MarketplaceListing.__table__, "current_price_amount")
    assert _has_check(MarketplaceListing.__table__, "seller_type_allowed")
    assert _has_check(
        MarketplaceListingObservation.__table__,
        "listed_price_non_negative",
    )
    assert _has_check(MarketplacePriceHistory.__table__, "price_amount")
    assert _has_check(RegistrationObservation.__table__, "sales_metric_type_allowed")
    assert _has_check(ExchangeRateObservation.__table__, "exchange_rate_positive")
    assert _has_check(
        EstimatedTransactionPrice.__table__,
        "estimated_transaction_price_non_negative",
    )
    assert _has_check(DataQualityIssue.__table__, "resolution_window_valid")


def test_all_indexes_reference_existing_columns() -> None:
    for table in Base.metadata.tables.values():
        columns = set(table.columns)
        for index in table.indexes:
            assert set(index.columns).issubset(columns), index.name


def test_bidirectional_relationships_configure() -> None:
    configure_mappers()

    expected_relationships = {
        DataSource: {
            "categories",
            "collection_batches",
            "official_price_observations",
            "marketplace_listings",
            "registration_observations",
            "exchange_rate_observations",
        },
        Vehicle: {
            "brand",
            "aliases",
            "variants",
            "marketplace_listings",
            "registration_observations",
        },
        VehicleVariant: {
            "vehicle",
            "official_price_observations",
            "marketplace_listings",
            "registration_observations",
            "estimated_transaction_prices",
        },
        MarketplaceListing: {
            "data_source",
            "vehicle",
            "vehicle_variant",
            "observations",
            "price_history",
            "estimated_transaction_prices",
        },
    }

    for model, relationship_names in expected_relationships.items():
        configured = set(sa_inspect(model).relationships.keys())
        assert relationship_names.issubset(configured)


def test_lifecycle_dependent_relationship_cascade_is_limited() -> None:
    assert DataSource.categories.property.cascade.delete_orphan
    assert Vehicle.aliases.property.cascade.delete_orphan
    assert not MarketplaceListing.observations.property.cascade.delete_orphan
    assert not VehicleVariant.official_price_observations.property.cascade.delete_orphan


def test_sqlite_memory_create_all_and_drop_all() -> None:
    before_files = _database_files()
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)
    inspector = sa_inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES

    Base.metadata.drop_all(engine)
    inspector = sa_inspect(engine)
    assert inspector.get_table_names() == []
    assert _database_files() == before_files


def test_numeric_fields_use_numeric_type() -> None:
    numeric_columns = [
        OfficialPriceObservation.__table__.c.official_price,
        MarketplaceListing.__table__.c.current_price_amount,
        MarketplaceListing.__table__.c.power_kw,
        MarketplaceListingObservation.__table__.c.listed_price,
        MarketplacePriceHistory.__table__.c.price_amount,
        RegistrationObservation.__table__.c.sales_value,
        RegistrationObservation.__table__.c.market_share,
        ExchangeRateObservation.__table__.c.exchange_rate,
        EstimatedTransactionPrice.__table__.c.estimated_transaction_price,
        VehicleVariant.__table__.c.battery_capacity_kwh,
        VehicleVariant.__table__.c.engine_power_kw,
        VehicleVariant.__table__.c.engine_power_ps,
    ]

    assert all(isinstance(column.type, Numeric) for column in numeric_columns)


def test_timestamp_fields_are_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_at") or column.name in {
                "started_at",
                "completed_at",
                "estimated_at",
                "detected_at",
                "resolved_at",
            }:
                assert isinstance(column.type, DateTime)
                assert column.type.timezone is True


def test_model_import_does_not_create_engine_or_database_files() -> None:
    assert getattr(Base.metadata, "bind", None) is None
    assert _database_files() == set()


def _unique_columns(table: object) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _has_check(table: object, name_part: str) -> bool:
    return any(
        name_part in str(constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )


def _database_files() -> set[Path]:
    patterns = ("*.db", "*.sqlite", "*.sqlite3")
    return {
        path
        for pattern in patterns
        for path in Path(".").rglob(pattern)
        if ".git" not in path.parts
    }
