"""Tests for read-only daily marketplace update monitoring."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from services.daily_updates import (
    clear_daily_update_summary_cache,
    load_daily_update_summary,
)


@pytest.fixture()
def update_database(tmp_path: Path) -> Path:
    path = tmp_path / "updates.sqlite3"
    connection = sqlite3.connect(path)
    _create_schema(connection)
    connection.executescript("""
        INSERT INTO collection_batches VALUES
            (1, 'previous-run', '2026-07-31T00:00:00',
             '2026-07-31T01:00:00', '2026-07-31T00:00:00', 1, 'completed'),
            (10, 'latest-run', '2026-08-01T00:00:00',
             '2026-08-01T00:30:00', '2026-08-01T00:00:00', 3, 'completed'),
            (11, 'latest-run', '2026-08-01T00:30:00',
             '2026-08-01T01:00:00', '2026-08-01T00:30:00', 2, 'completed');

        INSERT INTO marketplace_listings VALUES
            (1, 10, '2026-08-01T00:10:00', 1, '2026-08-01T00:15:00'),
            (2, 10, '2026-07-30T00:10:00', 1, '2026-08-01T00:40:00'),
            (3, 11, '2026-07-30T00:10:00', 0, '2026-08-01T00:45:00'),
            (4, NULL, '2026-07-30T00:10:00', 1, '2026-07-31T00:30:00');

        INSERT INTO marketplace_listing_observations VALUES
            (1, 4, 1, '2026-07-31T00:30:00', 'active'),
            (2, 1, 10, '2026-08-01T00:15:00', 'active'),
            (3, 2, 10, '2026-08-01T00:20:00', 'active'),
            (4, 3, 11, '2026-08-01T00:40:00', 'removed');

        INSERT INTO marketplace_price_history VALUES
            (1, 2, 100, '2026-07-31T00:30:00', '2026-07-31T00:30:00'),
            (2, 3, 50, '2026-07-31T00:30:00', '2026-07-31T00:30:00'),
            (3, 1, 200, '2026-08-01T00:15:00', '2026-08-01T00:15:00'),
            (4, 2, 90, '2026-08-01T00:20:00', '2026-08-01T00:20:00'),
            (5, 2, 95, '2026-08-01T00:40:00', '2026-08-01T00:40:00'),
            (6, 3, 40, '2026-08-01T00:45:00', '2026-08-01T00:45:00');
        """)
    connection.commit()
    connection.close()
    clear_daily_update_summary_cache()
    return path


def test_latest_run_metrics_and_price_direction_are_verifiable(
    update_database: Path,
) -> None:
    summary = load_daily_update_summary(update_database, history_days=7)

    assert summary.run_id == "latest-run"
    assert summary.last_successful_update_at == "2026-08-01T01:00:00"
    assert summary.listings_scanned == 5
    assert summary.new_listings == 1
    assert summary.existing_listings_updated == 2
    assert summary.price_changes == 3
    assert summary.price_decreases == 2
    assert summary.price_increases == 1
    assert summary.inactive_listings == 1
    assert summary.new_price_history_records == 4
    assert summary.vehicles_updated == 2

    latest_day = summary.history[-1]
    assert latest_day.update_date == "2026-08-01"
    assert latest_day.new_listings == 1
    assert latest_day.existing_listings_updated == 2
    assert latest_day.price_changes == 3
    assert latest_day.inactive_listings == 1


def test_empty_database_returns_explicit_missing_latest_run(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite3"
    connection = sqlite3.connect(path)
    _create_schema(connection)
    connection.close()
    clear_daily_update_summary_cache()

    summary = load_daily_update_summary(path)

    assert summary.run_id is None
    assert summary.listings_scanned is None
    assert summary.new_listings is None
    assert summary.price_changes is None
    assert summary.history == ()


@pytest.mark.parametrize("history_days", [0, 367, True, 7.0])
def test_history_window_rejects_invalid_values(
    update_database: Path,
    history_days: object,
) -> None:
    with pytest.raises(ValueError, match="history_days"):
        load_daily_update_summary(update_database, history_days=history_days)  # type: ignore[arg-type]


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE collection_batches (
            collection_batch_id INTEGER PRIMARY KEY,
            collection_job_id TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT,
            record_count INTEGER,
            status TEXT NOT NULL
        );
        CREATE TABLE marketplace_listings (
            marketplace_listing_id INTEGER PRIMARY KEY,
            vehicle_id INTEGER,
            first_seen_at TEXT,
            active INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE marketplace_listing_observations (
            marketplace_listing_observation_id INTEGER PRIMARY KEY,
            marketplace_listing_id INTEGER NOT NULL,
            collection_batch_id INTEGER,
            observed_at TEXT NOT NULL,
            listing_status TEXT NOT NULL
        );
        CREATE TABLE marketplace_price_history (
            marketplace_price_history_id INTEGER PRIMARY KEY,
            marketplace_listing_id INTEGER NOT NULL,
            price_amount NUMERIC NOT NULL,
            observed_at TEXT NOT NULL,
            collected_at TEXT
        );
        """)
