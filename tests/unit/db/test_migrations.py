from __future__ import annotations

import io
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.sql.schema import CheckConstraint, UniqueConstraint

from alembic import command
from germania.db import Base
from germania.db.settings import (
    DEFAULT_DATABASE_URL,
    GERMANIA_DATABASE_URL_ENV,
    get_database_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"
INITIAL_MIGRATION_REVISION = "26591d9c4240"
MIGRATION_REVISION = "8f4c2d9a1b6e"
EXPECTED_TABLES = set(Base.metadata.tables)
NETWORK_MARKERS = (
    "httpx",
    "requests",
    "urllib",
    "socket",
    "aiohttp",
    "playwright",
    "selenium",
)


def test_alembic_configuration_files_exist() -> None:
    assert ALEMBIC_INI.is_file()
    assert ALEMBIC_DIR.is_dir()
    assert (ALEMBIC_DIR / "env.py").is_file()
    assert (ALEMBIC_DIR / "script.py.mako").is_file()
    assert VERSIONS_DIR.is_dir()


def test_script_location_and_single_head_are_valid() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)

    assert len(list(VERSIONS_DIR.glob("*.py"))) == 2
    assert script.dir == str(ALEMBIC_DIR)
    assert script.get_heads() == [MIGRATION_REVISION]
    assert script.get_current_head() == MIGRATION_REVISION


def test_migration_revisions_have_upgrade_and_downgrade() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    initial_revision = script.get_revision(INITIAL_MIGRATION_REVISION)
    head_revision = script.get_revision(MIGRATION_REVISION)

    assert initial_revision is not None
    assert initial_revision.down_revision is None
    assert initial_revision.module.upgrade is not None
    assert initial_revision.module.downgrade is not None
    assert head_revision is not None
    assert head_revision.down_revision == INITIAL_MIGRATION_REVISION
    assert head_revision.module.upgrade is not None
    assert head_revision.module.downgrade is not None


def test_database_url_resolution_priority(monkeypatch: object) -> None:
    monkeypatch.setenv(GERMANIA_DATABASE_URL_ENV, "sqlite:///tmp/from_env.sqlite3")
    assert get_database_url("sqlite:///tmp/from_ini.sqlite3").endswith(
        "from_env.sqlite3"
    )

    monkeypatch.delenv(GERMANIA_DATABASE_URL_ENV)
    assert get_database_url("sqlite:///tmp/from_ini.sqlite3").endswith(
        "from_ini.sqlite3"
    )
    assert get_database_url("") == DEFAULT_DATABASE_URL


def test_upgrade_downgrade_upgrade_cycle_validates_schema(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database_path = tmp_path / "germania_migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv(GERMANIA_DATABASE_URL_ENV, database_url)
    config = _alembic_config(database_url)

    try:
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                assert (
                    connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                )

                inspector = inspect(connection)
                business_tables = _business_tables(inspector.get_table_names())
                assert business_tables == EXPECTED_TABLES
                assert len(business_tables) == 14
                assert "alembic_version" in inspector.get_table_names()
                assert _current_revision(connection) == MIGRATION_REVISION

                assert _foreign_key_count(inspector) == 21
                assert _required_foreign_keys_exist(inspector)
                assert _required_unique_constraints_exist(inspector)
                assert _required_indexes_exist(inspector)
                assert _required_check_constraints_exist(inspector)
                assert _kba_registration_columns_exist(inspector)
                assert _schema_matches_orm_metadata(inspector)
        finally:
            engine.dispose()

        command.downgrade(config, "base")
        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                inspector = inspect(connection)
                assert _business_tables(inspector.get_table_names()) == set()
        finally:
            engine.dispose()

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                inspector = inspect(connection)
                assert _business_tables(inspector.get_table_names()) == EXPECTED_TABLES
        finally:
            engine.dispose()
    finally:
        database_path.unlink(missing_ok=True)

    assert not database_path.exists()
    assert _project_database_or_sql_files() == set()


def test_offline_sql_generation_succeeds(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database_path = tmp_path / "offline.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv(GERMANIA_DATABASE_URL_ENV, database_url)
    output = io.StringIO()
    config = _alembic_config(database_url, output_buffer=output)

    command.upgrade(config, "head", sql=True)
    sql_text = output.getvalue()

    assert "CREATE TABLE data_sources" in sql_text
    assert "CREATE TABLE vehicles" in sql_text
    assert "CREATE TABLE marketplace_listing_observations" in sql_text
    assert "fuel_type" in sql_text
    assert "market_share" in sql_text
    assert "CREATE TABLE alembic_version" in sql_text
    assert not database_path.exists()


def test_migration_sources_do_not_import_network_clients() -> None:
    migration_files = [ALEMBIC_DIR / "env.py", *VERSIONS_DIR.glob("*.py")]
    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in migration_files
    )

    assert not any(marker in source_text for marker in NETWORK_MARKERS)


def test_project_directory_has_no_persistent_database_or_sql_files() -> None:
    assert _project_database_or_sql_files() == set()


def _alembic_config(
    database_url: str | None = None,
    output_buffer: io.StringIO | None = None,
) -> Config:
    config = Config(str(ALEMBIC_INI), output_buffer=output_buffer)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def _business_tables(table_names: list[str]) -> set[str]:
    return {table_name for table_name in table_names if table_name != "alembic_version"}


def _current_revision(connection: object) -> str | None:
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _foreign_key_count(inspector: object) -> int:
    return sum(
        len(inspector.get_foreign_keys(table_name)) for table_name in EXPECTED_TABLES
    )


def _required_foreign_keys_exist(inspector: object) -> bool:
    foreign_keys = {
        (
            table_name,
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for table_name in EXPECTED_TABLES
        for foreign_key in inspector.get_foreign_keys(table_name)
    }

    expected_foreign_keys = {
        ("vehicles", ("brand_id",), "brands", ("brand_id",)),
        ("vehicle_aliases", ("vehicle_id",), "vehicles", ("vehicle_id",)),
        ("vehicle_variants", ("vehicle_id",), "vehicles", ("vehicle_id",)),
        (
            "marketplace_listing_observations",
            ("marketplace_listing_id",),
            "marketplace_listings",
            ("marketplace_listing_id",),
        ),
        (
            "estimated_transaction_prices",
            ("marketplace_listing_observation_id",),
            "marketplace_listing_observations",
            ("marketplace_listing_observation_id",),
        ),
        (
            "registration_observations",
            ("brand_id",),
            "brands",
            ("brand_id",),
        ),
    }
    return expected_foreign_keys.issubset(foreign_keys)


def _required_unique_constraints_exist(inspector: object) -> bool:
    unique_constraints = {
        (table_name, tuple(unique_constraint["column_names"]))
        for table_name in EXPECTED_TABLES
        for unique_constraint in inspector.get_unique_constraints(table_name)
    }

    required = {
        ("data_sources", ("source_id",)),
        ("brands", ("canonical_brand",)),
        ("vehicles", ("brand_id", "canonical_model")),
        ("vehicle_aliases", ("normalized_alias",)),
        ("marketplace_listings", ("data_source_id", "source_listing_id")),
        (
            "marketplace_listing_observations",
            ("marketplace_listing_id", "observed_at"),
        ),
        (
            "exchange_rate_observations",
            (
                "data_source_id",
                "base_currency",
                "quote_currency",
                "exchange_rate_date",
            ),
        ),
        ("collection_batches", ("batch_id",)),
        (
            "registration_observations",
            (
                "data_source_id",
                "brand_id",
                "vehicle_id",
                "registration_period",
                "fuel_type",
            ),
        ),
    }
    return required.issubset(unique_constraints)


def _required_indexes_exist(inspector: object) -> bool:
    indexes = {
        index["name"]
        for table_name in EXPECTED_TABLES
        for index in inspector.get_indexes(table_name)
    }

    required = {
        "ix_vehicles_brand_model",
        "ix_vehicle_aliases_normalized_alias",
        "ix_marketplace_listings_source_listing",
        "ix_marketplace_listing_observations_listing_observed",
        "ix_exchange_rate_observations_source_pair_date",
        "ix_data_quality_issues_entity",
    }
    return required.issubset(indexes)


def _required_check_constraints_exist(inspector: object) -> bool:
    check_constraints = {
        check_constraint["name"]
        for table_name in EXPECTED_TABLES
        for check_constraint in inspector.get_check_constraints(table_name)
    }

    required = {
        "ck_data_sources_source_type_allowed",
        "ck_vehicles_priority_level_allowed",
        "ck_vehicle_aliases_alias_type_allowed",
        "ck_official_price_observations_official_price_non_negative",
        "ck_marketplace_listing_observations_listed_price_non_negative",
        "ck_registration_observations_sales_metric_type_allowed",
        "ck_exchange_rate_observations_exchange_rate_positive",
        "ck_estimated_transaction_prices_confidence_level_allowed",
    }
    return required.issubset(check_constraints)


def _kba_registration_columns_exist(inspector: object) -> bool:
    columns = {
        column["name"]: column
        for column in inspector.get_columns("registration_observations")
    }
    return {
        "brand_id",
        "fuel_type",
        "market_share",
    }.issubset(columns)


def _schema_matches_orm_metadata(inspector: object) -> bool:
    for table_name, orm_table in Base.metadata.tables.items():
        inspected_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        orm_columns = set(orm_table.columns.keys())
        if inspected_columns != orm_columns:
            return False

        inspected_pk = tuple(
            inspector.get_pk_constraint(table_name)["constrained_columns"]
        )
        orm_pk = tuple(column.name for column in orm_table.primary_key.columns)
        if inspected_pk != orm_pk:
            return False

        inspected_indexes = {
            index["name"] for index in inspector.get_indexes(table_name)
        }
        orm_indexes = {index.name for index in orm_table.indexes}
        if inspected_indexes != orm_indexes:
            return False

        inspected_unique = {
            tuple(unique_constraint["column_names"])
            for unique_constraint in inspector.get_unique_constraints(table_name)
        }
        orm_unique = {
            tuple(column.name for column in constraint.columns)
            for constraint in orm_table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        if not orm_unique.issubset(inspected_unique):
            return False

        inspected_checks = {
            check_constraint["name"]
            for check_constraint in inspector.get_check_constraints(table_name)
        }
        orm_checks = {
            constraint.name
            for constraint in orm_table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        if not all(
            _resolved_check_name(table_name, name) in inspected_checks
            for name in orm_checks
        ):
            return False

    return True


def _resolved_check_name(table_name: str, check_name: str) -> str:
    if check_name.startswith(f"ck_{table_name}_"):
        return check_name
    return f"ck_{table_name}_{check_name}"


def _project_database_or_sql_files() -> set[Path]:
    patterns = ("*.db", "*.sqlite", "*.sqlite3", "*.sql")
    return {
        path
        for pattern in patterns
        for path in PROJECT_ROOT.rglob(pattern)
        if ".git" not in path.parts
    }
