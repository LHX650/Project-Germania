from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from services.database import (
    clear_comparable_vehicle_metadata_cache,
    get_connection,
    list_listing_brands,
    load_comparable_vehicle_metadata,
    search_listings,
)


@pytest.fixture()
def listing_database(tmp_path: Path) -> Path:
    path = tmp_path / "listings.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE marketplace_listings (
            marketplace_listing_id INTEGER PRIMARY KEY,
            external_listing_id TEXT NOT NULL,
            brand_name TEXT,
            model_name TEXT,
            title TEXT,
            current_price_amount NUMERIC,
            currency TEXT NOT NULL,
            mileage_km INTEGER,
            fuel_type TEXT,
            registration_year INTEGER,
            seller_city TEXT,
            active INTEGER NOT NULL,
            last_collected_at TEXT,
            listing_url TEXT
        );
        INSERT INTO marketplace_listings VALUES
            (1, 'alpha-1', 'Dynamic Motors', 'Alpha', 'Alpha 100% electric',
             20000, 'EUR', 10000, 'electric', 2024, 'Berlin', 1,
             '2026-07-31T10:00:00', 'https://example.test/alpha-1'),
            (2, 'beta-1', 'Dynamic Motors', 'Beta', 'Beta plug-in hybrid',
             35000, 'EUR', 5000, 'phev', 2025, 'Hamburg', 1,
             '2026-07-31T11:00:00', 'https://example.test/beta-1'),
            (3, 'legacy-1', 'Legacy Auto', 'Classic', 'Legacy Classic',
             15000, 'EUR', 50000, 'petrol', 2020, 'Munich', 0,
             '2026-07-30T11:00:00', 'https://example.test/legacy-1');
        """)
    connection.commit()
    connection.close()
    return path


def test_dynamic_brand_and_parameterized_listing_filters(
    listing_database: Path,
) -> None:
    assert list_listing_brands(listing_database) == (
        "Dynamic Motors",
        "Legacy Auto",
    )

    results = search_listings(
        listing_database,
        brand="dynamic motors",
        minimum_price=Decimal("25000"),
        active_only=True,
    )

    assert len(results) == 1
    assert results[0].external_listing_id == "beta-1"
    assert results[0].current_price_amount == Decimal("35000")
    assert results[0].active is True


def test_query_escapes_wildcards_and_does_not_execute_sql(
    listing_database: Path,
) -> None:
    wildcard_results = search_listings(listing_database, query="100%")
    injection_results = search_listings(
        listing_database,
        query="'; DROP TABLE marketplace_listings; --",
    )

    assert [item.external_listing_id for item in wildcard_results] == ["alpha-1"]
    assert injection_results == ()
    assert len(search_listings(listing_database, active_only=False)) == 3


def test_connection_rejects_database_writes(listing_database: Path) -> None:
    with get_connection(listing_database) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE marketplace_listings SET active = 0 WHERE 1 = 0")


def test_invalid_price_range_and_limit_are_rejected(
    listing_database: Path,
) -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        search_listings(
            listing_database,
            minimum_price=20_000,
            maximum_price=10_000,
        )
    with pytest.raises(ValueError, match="between 1 and 1000"):
        search_listings(listing_database, limit=0)


def test_comparable_controls_load_read_only_and_invalidate_on_file_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "metadata.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE brands (
            brand_id INTEGER PRIMARY KEY,
            canonical_brand TEXT NOT NULL,
            country_of_origin TEXT,
            active INTEGER NOT NULL
        );
        CREATE TABLE vehicles (
            vehicle_id INTEGER PRIMARY KEY,
            brand_id INTEGER NOT NULL,
            canonical_model TEXT NOT NULL,
            vehicle_segment TEXT,
            body_type TEXT,
            default_powertrain TEXT,
            active INTEGER NOT NULL
        );
        INSERT INTO brands VALUES (1, 'Dynamic Motors', 'Germany', 1);
        INSERT INTO vehicles VALUES
            (1, 1, 'Alpha', 'compact_suv', 'suv', 'battery_electric', 1);
        """)
    connection.commit()
    connection.close()
    clear_comparable_vehicle_metadata_cache()

    first = load_comparable_vehicle_metadata(path)

    assert len(first) == 1
    assert first[0].vehicle_key == "Dynamic Motors Alpha"
    assert first[0].vehicle_segment == "compact_suv"
    assert first[0].powertrain == "battery_electric"
    assert first[0].market_attribute == "Germany"

    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO vehicles VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, 1, "Beta", "compact_suv", "suv", "battery_electric", 1),
    )
    connection.commit()
    connection.close()

    refreshed = load_comparable_vehicle_metadata(path)
    assert [item.model_name for item in refreshed] == ["Alpha", "Beta"]
