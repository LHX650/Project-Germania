"""Read-only daily marketplace update metrics for the Data Quality page."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from services.database import get_connection, resolve_database_path


@dataclass(frozen=True)
class DailyUpdatePoint:
    """One UTC calendar day's verifiable marketplace update activity."""

    update_date: str
    listings_scanned: int
    new_listings: int
    existing_listings_updated: int
    price_changes: int
    price_decreases: int
    price_increases: int
    inactive_listings: int
    new_price_history_records: int
    vehicles_updated: int


@dataclass(frozen=True)
class DailyUpdateSummary:
    """Latest collection-run metrics plus bounded daily history."""

    run_id: str | None
    started_at: str | None
    completed_at: str | None
    last_successful_update_at: str | None
    listings_scanned: int | None
    new_listings: int | None
    existing_listings_updated: int | None
    price_changes: int | None
    price_decreases: int | None
    price_increases: int | None
    inactive_listings: int | None
    new_price_history_records: int | None
    vehicles_updated: int | None
    history: tuple[DailyUpdatePoint, ...]


def load_daily_update_summary(
    database_path: str | Path | None = None,
    *,
    history_days: int = 30,
) -> DailyUpdateSummary:
    """Load latest-run and daily metrics from an mtime-aware read-only cache."""

    if (
        isinstance(history_days, bool)
        or not isinstance(history_days, int)
        or not 1 <= history_days <= 366
    ):
        raise ValueError("history_days must be an integer between 1 and 366")
    path = resolve_database_path(database_path)
    if not path.is_file():
        raise FileNotFoundError(
            "Project Germania SQLite database was not found at "
            f"'{path}'. A database file will not be created automatically."
        )
    stat = path.stat()
    return _load_daily_update_summary_cached(
        str(path), stat.st_mtime_ns, stat.st_size, history_days
    )


def clear_daily_update_summary_cache() -> None:
    """Clear the bounded cache for tests or an explicit Dashboard refresh."""

    _load_daily_update_summary_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_daily_update_summary_cached(
    path_text: str,
    modified_at_ns: int,
    file_size: int,
    history_days: int,
) -> DailyUpdateSummary:
    del modified_at_ns, file_size
    with get_connection(path_text) as connection:
        latest = _latest_run(connection)
        history = _daily_history(connection, history_days)
        last_successful_update_at = _last_successful_update(connection)
        if latest is None:
            return DailyUpdateSummary(
                run_id=None,
                started_at=None,
                completed_at=None,
                last_successful_update_at=last_successful_update_at,
                listings_scanned=None,
                new_listings=None,
                existing_listings_updated=None,
                price_changes=None,
                price_decreases=None,
                price_increases=None,
                inactive_listings=None,
                new_price_history_records=None,
                vehicles_updated=None,
                history=history,
            )

        run_id = str(latest["collection_job_id"])
        started_at = _optional_text(latest["started_at"])
        completed_at = _optional_text(latest["completed_at"])
        observation_metrics = _latest_observation_metrics(connection, run_id)
        price_metrics = _latest_price_metrics(connection, started_at, completed_at)

    return DailyUpdateSummary(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        last_successful_update_at=last_successful_update_at,
        listings_scanned=_optional_int(latest["listings_scanned"]),
        new_listings=int(observation_metrics["new_listings"]),
        existing_listings_updated=int(observation_metrics["existing_listings_updated"]),
        price_changes=price_metrics["price_changes"],
        price_decreases=price_metrics["price_decreases"],
        price_increases=price_metrics["price_increases"],
        inactive_listings=int(observation_metrics["inactive_listings"]),
        new_price_history_records=price_metrics["history_records"],
        vehicles_updated=int(observation_metrics["vehicles_updated"]),
        history=history,
    )


def _latest_run(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute("""
        WITH latest_job AS (
            SELECT collection_job_id
            FROM collection_batches
            WHERE collection_job_id IS NOT NULL
              AND trim(collection_job_id) <> ''
            ORDER BY COALESCE(completed_at, started_at, created_at) DESC,
                     collection_batch_id DESC
            LIMIT 1
        )
        SELECT
            b.collection_job_id,
            MIN(b.started_at) AS started_at,
            MAX(b.completed_at) AS completed_at,
            CASE
                WHEN COUNT(b.record_count) = 0 THEN NULL
                ELSE SUM(b.record_count)
            END AS listings_scanned
        FROM collection_batches AS b
        JOIN latest_job AS j ON j.collection_job_id = b.collection_job_id
        GROUP BY b.collection_job_id
    """).fetchone()


def _last_successful_update(connection: sqlite3.Connection) -> str | None:
    value = connection.execute("""
        SELECT MAX(completed_at)
        FROM collection_batches
        WHERE status = 'completed' AND completed_at IS NOT NULL
        """).fetchone()[0]
    return _optional_text(value)


def _latest_observation_metrics(
    connection: sqlite3.Connection,
    run_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        WITH run_observations AS (
            SELECT DISTINCT
                o.marketplace_listing_id,
                o.listing_status,
                o.observed_at,
                l.first_seen_at,
                l.vehicle_id
            FROM marketplace_listing_observations AS o
            JOIN collection_batches AS b
              ON b.collection_batch_id = o.collection_batch_id
            JOIN marketplace_listings AS l
              ON l.marketplace_listing_id = o.marketplace_listing_id
            WHERE b.collection_job_id = ?
        ), run_bounds AS (
            SELECT MIN(started_at) AS started_at, MAX(completed_at) AS completed_at
            FROM collection_batches
            WHERE collection_job_id = ?
        ), inactive_ids AS (
            SELECT marketplace_listing_id
            FROM run_observations
            WHERE listing_status IN ('removed', 'sold', 'unavailable')
            UNION
            SELECT l.marketplace_listing_id
            FROM marketplace_listings AS l, run_bounds AS bounds
            WHERE l.active = 0
              AND bounds.started_at IS NOT NULL
              AND bounds.completed_at IS NOT NULL
              AND datetime(l.updated_at) BETWEEN datetime(bounds.started_at)
                                             AND datetime(bounds.completed_at)
        )
        SELECT
            COUNT(DISTINCT CASE
                WHEN first_seen_at IS NOT NULL
                 AND date(first_seen_at) = date(observed_at)
                THEN marketplace_listing_id
            END) AS new_listings,
            COUNT(DISTINCT marketplace_listing_id)
              - COUNT(DISTINCT CASE
                    WHEN first_seen_at IS NOT NULL
                     AND date(first_seen_at) = date(observed_at)
                    THEN marketplace_listing_id
                END) AS existing_listings_updated,
            (SELECT COUNT(*) FROM inactive_ids) AS inactive_listings,
            COUNT(DISTINCT vehicle_id) AS vehicles_updated
        FROM run_observations, run_bounds AS bounds
        """,
        (run_id, run_id),
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("Unable to aggregate latest observations")
    return row


def _latest_price_metrics(
    connection: sqlite3.Connection,
    started_at: str | None,
    completed_at: str | None,
) -> dict[str, int | None]:
    if started_at is None or completed_at is None:
        return {
            "history_records": None,
            "price_changes": None,
            "price_decreases": None,
            "price_increases": None,
        }
    row = connection.execute(
        """
        WITH sequenced AS (
            SELECT
                price_amount,
                COALESCE(collected_at, observed_at) AS event_at,
                LAG(price_amount) OVER (
                    PARTITION BY marketplace_listing_id
                    ORDER BY datetime(observed_at), marketplace_price_history_id
                ) AS previous_price
            FROM marketplace_price_history
        )
        SELECT
            COUNT(*) AS history_records,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount <> previous_price
                THEN 1 ELSE 0
            END) AS price_changes,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount < previous_price
                THEN 1 ELSE 0
            END) AS price_decreases,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount > previous_price
                THEN 1 ELSE 0
            END) AS price_increases
        FROM sequenced
        WHERE datetime(event_at) BETWEEN datetime(?) AND datetime(?)
        """,
        (started_at, completed_at),
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("Unable to aggregate latest price history")
    return {
        "history_records": int(row["history_records"]),
        "price_changes": int(row["price_changes"] or 0),
        "price_decreases": int(row["price_decreases"] or 0),
        "price_increases": int(row["price_increases"] or 0),
    }


def _daily_history(
    connection: sqlite3.Connection,
    history_days: int,
) -> tuple[DailyUpdatePoint, ...]:
    anchor_value = connection.execute("""
        SELECT MAX(event_date)
        FROM (
            SELECT
                date(MAX(COALESCE(completed_at, started_at, created_at))) AS event_date
            FROM collection_batches
            UNION ALL
            SELECT date(MAX(observed_at)) FROM marketplace_listing_observations
            UNION ALL
            SELECT date(MAX(COALESCE(collected_at, observed_at)))
            FROM marketplace_price_history
        )
        """).fetchone()[0]
    if anchor_value is None:
        return ()
    anchor = date.fromisoformat(str(anchor_value))
    first_day = (anchor - timedelta(days=history_days - 1)).isoformat()
    last_day = anchor.isoformat()

    day_values: dict[str, dict[str, int]] = {}
    _merge_batch_history(connection, day_values, first_day, last_day)
    _merge_observation_history(connection, day_values, first_day, last_day)
    _merge_price_history(connection, day_values, first_day, last_day)
    return tuple(
        DailyUpdatePoint(update_date=day, **values)
        for day, values in sorted(day_values.items())
    )


def _empty_day() -> dict[str, int]:
    return {
        "listings_scanned": 0,
        "new_listings": 0,
        "existing_listings_updated": 0,
        "price_changes": 0,
        "price_decreases": 0,
        "price_increases": 0,
        "inactive_listings": 0,
        "new_price_history_records": 0,
        "vehicles_updated": 0,
    }


def _merge_batch_history(
    connection: sqlite3.Connection,
    values: dict[str, dict[str, int]],
    first_day: str,
    last_day: str,
) -> None:
    rows = connection.execute(
        """
        SELECT
            date(COALESCE(completed_at, started_at, created_at)) AS event_date,
            SUM(COALESCE(record_count, 0)) AS listings_scanned
        FROM collection_batches
        WHERE date(COALESCE(completed_at, started_at, created_at)) BETWEEN ? AND ?
        GROUP BY event_date
        """,
        (first_day, last_day),
    ).fetchall()
    for row in rows:
        day = str(row["event_date"])
        values.setdefault(day, _empty_day())["listings_scanned"] = int(
            row["listings_scanned"] or 0
        )


def _merge_observation_history(
    connection: sqlite3.Connection,
    values: dict[str, dict[str, int]],
    first_day: str,
    last_day: str,
) -> None:
    rows = connection.execute(
        """
        WITH observed AS (
            SELECT
                date(o.observed_at) AS event_date,
                o.marketplace_listing_id,
                o.listing_status,
                l.first_seen_at,
                l.vehicle_id
            FROM marketplace_listing_observations AS o
            JOIN marketplace_listings AS l
              ON l.marketplace_listing_id = o.marketplace_listing_id
            WHERE date(o.observed_at) BETWEEN ? AND ?
        ), inactive_events AS (
            SELECT event_date, marketplace_listing_id
            FROM observed
            WHERE listing_status IN ('removed', 'sold', 'unavailable')
            UNION
            SELECT date(updated_at), marketplace_listing_id
            FROM marketplace_listings
            WHERE active = 0 AND date(updated_at) BETWEEN ? AND ?
        ), inactive_counts AS (
            SELECT event_date, COUNT(DISTINCT marketplace_listing_id) AS count
            FROM inactive_events
            GROUP BY event_date
        )
        SELECT
            observed.event_date,
            COUNT(DISTINCT CASE
                WHEN date(first_seen_at) = observed.event_date
                THEN marketplace_listing_id
            END) AS new_listings,
            COUNT(DISTINCT marketplace_listing_id)
              - COUNT(DISTINCT CASE
                    WHEN date(first_seen_at) = observed.event_date
                    THEN marketplace_listing_id
                END) AS existing_listings_updated,
            COUNT(DISTINCT vehicle_id) AS vehicles_updated,
            COALESCE(MAX(inactive_counts.count), 0) AS inactive_listings
        FROM observed
        LEFT JOIN inactive_counts
          ON inactive_counts.event_date = observed.event_date
        GROUP BY observed.event_date
        """,
        (first_day, last_day, first_day, last_day),
    ).fetchall()
    for row in rows:
        day = str(row["event_date"])
        target = values.setdefault(day, _empty_day())
        for key in (
            "new_listings",
            "existing_listings_updated",
            "vehicles_updated",
            "inactive_listings",
        ):
            target[key] = int(row[key] or 0)


def _merge_price_history(
    connection: sqlite3.Connection,
    values: dict[str, dict[str, int]],
    first_day: str,
    last_day: str,
) -> None:
    rows = connection.execute(
        """
        WITH sequenced AS (
            SELECT
                date(COALESCE(collected_at, observed_at)) AS event_date,
                price_amount,
                LAG(price_amount) OVER (
                    PARTITION BY marketplace_listing_id
                    ORDER BY datetime(observed_at), marketplace_price_history_id
                ) AS previous_price
            FROM marketplace_price_history
        )
        SELECT
            event_date,
            COUNT(*) AS new_price_history_records,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount <> previous_price
                THEN 1 ELSE 0
            END) AS price_changes,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount < previous_price
                THEN 1 ELSE 0
            END) AS price_decreases,
            SUM(CASE
                WHEN previous_price IS NOT NULL AND price_amount > previous_price
                THEN 1 ELSE 0
            END) AS price_increases
        FROM sequenced
        WHERE event_date BETWEEN ? AND ?
        GROUP BY event_date
        """,
        (first_day, last_day),
    ).fetchall()
    for row in rows:
        day = str(row["event_date"])
        target = values.setdefault(day, _empty_day())
        for key in (
            "new_price_history_records",
            "price_changes",
            "price_decreases",
            "price_increases",
        ):
            target[key] = int(row[key] or 0)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
