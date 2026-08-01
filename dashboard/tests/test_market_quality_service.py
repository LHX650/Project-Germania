"""Tests for read-only deep-analysis and data-quality SQLite queries."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from services.database import (
    count_new_listings_on,
    load_database_quality,
    load_vehicle_analysis,
)


@pytest.fixture()
def intelligence_database(tmp_path: Path) -> Path:
    path = tmp_path / "intelligence.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE marketplace_listings (
            marketplace_listing_id INTEGER PRIMARY KEY,
            external_listing_id TEXT NOT NULL,
            brand_name TEXT,
            model_name TEXT,
            current_price_amount NUMERIC,
            currency TEXT,
            mileage_km INTEGER,
            registration_year INTEGER,
            active INTEGER NOT NULL,
            first_seen_at TEXT,
            last_collected_at TEXT,
            listing_url TEXT
        );
        CREATE TABLE marketplace_listing_observations (
            marketplace_listing_observation_id INTEGER PRIMARY KEY,
            marketplace_listing_id INTEGER NOT NULL,
            listed_price NUMERIC,
            currency TEXT,
            observed_at TEXT NOT NULL,
            listing_status TEXT NOT NULL
        );
        CREATE TABLE marketplace_price_history (
            marketplace_price_history_id INTEGER PRIMARY KEY
        );
        CREATE TABLE data_quality_issues (
            data_quality_issue_id INTEGER PRIMARY KEY
        );
        CREATE TABLE collection_batches (
            collection_batch_id INTEGER PRIMARY KEY,
            collection_job_id TEXT,
            status TEXT,
            success_count INTEGER,
            failure_count INTEGER,
            notes TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT
        );
        INSERT INTO marketplace_listings VALUES
            (1, 'alpha-1', 'Dynamic Motors', 'Alpha', 20000, 'EUR', 10000,
             2024, 1, '2026-08-01T00:10:00', '2026-08-01T01:00:00',
             'https://example.test/alpha-1'),
            (2, 'alpha-2', 'Dynamic Motors', 'Alpha', 30000, 'EUR', NULL,
             2025, 1, '2026-07-31T00:10:00', '2026-08-01T01:00:00',
             'https://example.test/alpha-2'),
            (3, 'beta-1', 'Dynamic Motors', 'Beta', 15000, 'EUR', 50000,
             2020, 0, '2026-07-30T00:10:00', '2026-07-31T01:00:00', NULL);
        INSERT INTO marketplace_listing_observations VALUES
            (1, 1, 21000, 'EUR', '2026-07-31T01:00:00', 'active'),
            (2, 2, 31000, 'EUR', '2026-07-31T01:00:00', 'active'),
            (3, 1, 20000, 'EUR', '2026-08-01T01:00:00', 'active'),
            (4, 2, 30000, 'EUR', '2026-08-01T01:00:00', 'active');
        INSERT INTO marketplace_price_history VALUES (1), (2);
        INSERT INTO data_quality_issues VALUES (1);
        """)
    notes = json.dumps(
        {
            "requested_pages": 2,
            "succeeded_pages": 2,
            "matched": 2,
            "rejected": 1,
            "low_confidence": 1,
            "import_rejected": 0,
        }
    )
    connection.execute(
        """
        INSERT INTO collection_batches VALUES
            (1, 'daily-fixture', 'completed', 2, 0, ?,
             '2026-08-01T00:00:00', '2026-08-01T01:00:00',
             '2026-08-01T00:00:00')
        """,
        (notes,),
    )
    connection.commit()
    connection.close()
    return path


def test_vehicle_analysis_and_daily_new_listing_count(
    intelligence_database: Path,
) -> None:
    snapshot = load_vehicle_analysis(
        "dynamic motors",
        "alpha",
        intelligence_database,
    )

    assert snapshot.active_listing_count == 2
    assert float(snapshot.average_price_eur or 0) == pytest.approx(25_000)
    assert snapshot.minimum_price_eur == 20_000
    assert snapshot.maximum_price_eur == 30_000
    assert len(snapshot.trend) == 2
    assert snapshot.trend[-1].observed_active_inventory == 2
    assert snapshot.mileages_km == (10_000,)
    assert count_new_listings_on(date(2026, 8, 1), intelligence_database) == 1


def test_database_quality_uses_latest_run_and_explicit_completeness(
    intelligence_database: Path,
) -> None:
    quality = load_database_quality(intelligence_database)

    assert quality.listings_count == 3
    assert quality.active_listings_count == 2
    assert quality.observations_count == 4
    assert quality.price_history_count == 2
    assert quality.quality_issue_count == 1
    assert quality.latest_run_id == "daily-fixture"
    assert quality.task_success_rate_pct == 100
    assert quality.page_success_rate_pct == 100
    assert quality.matched_count == 2
    assert quality.rejected_count == 1
    assert quality.low_confidence_count == 1
    assert quality.field_completeness_pct["Source URL"] == pytest.approx(200 / 3)
    assert quality.field_completeness_pct["Mileage"] == pytest.approx(200 / 3)
