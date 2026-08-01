"""Read-only SQLite access and parameterized marketplace listing queries."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.runtime import get_dashboard_data_paths

DEFAULT_DATABASE_RELATIVE_PATH = Path("database/project_germania_live.sqlite3")


@dataclass(frozen=True)
class ListingSearchResult:
    """One marketplace listing returned by the read-only Search Center."""

    external_listing_id: str
    brand_name: str | None
    model_name: str | None
    title: str | None
    current_price_amount: Decimal | None
    currency: str
    mileage_km: int | None
    fuel_type: str | None
    registration_year: int | None
    seller_city: str | None
    active: bool
    last_collected_at: str | None
    listing_url: str | None


@dataclass(frozen=True)
class VehicleTrendPoint:
    """One daily read-only marketplace observation aggregate."""

    observed_date: str
    average_price_eur: Decimal | None
    observed_active_inventory: int


@dataclass(frozen=True)
class VehicleAnalysisSnapshot:
    """Database-backed distributions and history for one canonical vehicle."""

    brand_name: str
    model_name: str
    active_listing_count: int
    average_price_eur: Decimal | None
    minimum_price_eur: Decimal | None
    maximum_price_eur: Decimal | None
    prices_eur: tuple[Decimal, ...]
    mileages_km: tuple[int, ...]
    registration_years: tuple[int, ...]
    trend: tuple[VehicleTrendPoint, ...]


@dataclass(frozen=True)
class ComparableVehicleMetadata:
    """Existing canonical control variables loaded read-only from SQLite."""

    vehicle_key: str
    brand_name: str
    model_name: str
    vehicle_segment: str | None
    body_type: str | None
    powertrain: str | None
    market_attribute: str | None


@dataclass(frozen=True)
class DatabaseQualitySnapshot:
    """Latest collection and database quality signals for the Dashboard."""

    listings_count: int
    active_listings_count: int
    observations_count: int
    price_history_count: int
    quality_issue_count: int
    latest_updated_at: str | None
    latest_run_id: str | None
    task_count: int
    successful_task_count: int
    task_success_rate_pct: float | None
    requested_pages: int
    succeeded_pages: int
    page_success_rate_pct: float | None
    matched_count: int
    rejected_count: int
    low_confidence_count: int
    import_rejected_count: int
    field_completeness_pct: dict[str, float | None]


def get_project_root() -> Path:
    """Return the absolute Project Germania root directory."""

    return Path(__file__).resolve().parents[2]


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    """Resolve a database path without creating a file or opening a connection."""

    candidate = (
        Path(database_path).expanduser()
        if database_path is not None
        else get_dashboard_data_paths().database
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return candidate.resolve(strict=False)


def database_exists(database_path: str | Path | None = None) -> bool:
    """Return whether the resolved SQLite database is an existing file."""

    return resolve_database_path(database_path).is_file()


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open an existing SQLite database with URI-enforced read-only access.

    The function never creates a missing database. Phase 17A defines this
    interface but does not call it from any page.
    """

    resolved_path = resolve_database_path(database_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(
            "Project Germania SQLite database was not found at "
            f"'{resolved_path}'. A database file will not be created automatically."
        )

    read_only_uri = f"{resolved_path.as_uri()}?mode=ro"
    connection = sqlite3.connect(read_only_uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def list_listing_brands(
    database_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return dynamically observed listing brands from the read-only database."""

    with get_connection(database_path) as connection:
        rows = connection.execute("""
            SELECT DISTINCT brand_name
            FROM marketplace_listings
            WHERE brand_name IS NOT NULL AND trim(brand_name) <> ''
            ORDER BY brand_name COLLATE NOCASE
            """).fetchall()
    return tuple(str(row["brand_name"]) for row in rows)


def search_listings(
    database_path: str | Path | None = None,
    *,
    query: str = "",
    brand: str | None = None,
    minimum_price: Decimal | int | None = None,
    maximum_price: Decimal | int | None = None,
    active_only: bool = True,
    limit: int = 200,
) -> tuple[ListingSearchResult, ...]:
    """Return parameterized marketplace listing results without database writes."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    minimum = _optional_non_negative_decimal(minimum_price, "minimum_price")
    maximum = _optional_non_negative_decimal(maximum_price, "maximum_price")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("minimum_price cannot exceed maximum_price")

    conditions: list[str] = []
    parameters: list[Any] = []
    normalized_query = " ".join(query.strip().split())
    if normalized_query:
        pattern = f"%{_escape_like(normalized_query)}%"
        conditions.append(
            "("
            "external_listing_id LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "brand_name LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "model_name LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "title LIKE ? ESCAPE '\\' COLLATE NOCASE"
            ")"
        )
        parameters.extend([pattern, pattern, pattern, pattern])
    normalized_brand = " ".join((brand or "").strip().split())
    if normalized_brand:
        conditions.append("brand_name = ? COLLATE NOCASE")
        parameters.append(normalized_brand)
    if minimum is not None:
        conditions.append("current_price_amount >= ?")
        parameters.append(str(minimum))
    if maximum is not None:
        conditions.append("current_price_amount <= ?")
        parameters.append(str(maximum))
    if active_only:
        conditions.append("active = 1")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT
            external_listing_id,
            brand_name,
            model_name,
            title,
            current_price_amount,
            currency,
            mileage_km,
            fuel_type,
            registration_year,
            seller_city,
            active,
            last_collected_at,
            listing_url
        FROM marketplace_listings
        {where_clause}
        ORDER BY last_collected_at DESC, marketplace_listing_id DESC
        LIMIT ?
    """
    parameters.append(limit)
    with get_connection(database_path) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return tuple(_listing_result(row) for row in rows)


def count_new_listings_on(
    report_date: date,
    database_path: str | Path | None = None,
) -> int:
    """Count listings first observed on one report date without writing data."""

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS listing_count
            FROM marketplace_listings
            WHERE date(first_seen_at) = ?
            """,
            (report_date.isoformat(),),
        ).fetchone()
    return int(row["listing_count"])


def load_vehicle_analysis(
    brand_name: str,
    model_name: str,
    database_path: str | Path | None = None,
) -> VehicleAnalysisSnapshot:
    """Load exact brand/model distributions and observation trends read-only."""

    normalized_brand = " ".join(brand_name.split())
    normalized_model = " ".join(model_name.split())
    if not normalized_brand or not normalized_model:
        raise ValueError("brand_name and model_name must be non-empty")
    parameters = (normalized_brand, normalized_model)
    with get_connection(database_path) as connection:
        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS active_listing_count,
                AVG(CASE WHEN currency = 'EUR' THEN current_price_amount END)
                    AS average_price_eur,
                MIN(CASE WHEN currency = 'EUR' THEN current_price_amount END)
                    AS minimum_price_eur,
                MAX(CASE WHEN currency = 'EUR' THEN current_price_amount END)
                    AS maximum_price_eur
            FROM marketplace_listings
            WHERE active = 1
              AND brand_name = ? COLLATE NOCASE
              AND model_name = ? COLLATE NOCASE
            """,
            parameters,
        ).fetchone()
        distribution_rows = connection.execute(
            """
            SELECT current_price_amount, currency, mileage_km, registration_year
            FROM marketplace_listings
            WHERE active = 1
              AND brand_name = ? COLLATE NOCASE
              AND model_name = ? COLLATE NOCASE
            ORDER BY marketplace_listing_id
            """,
            parameters,
        ).fetchall()
        trend_rows = connection.execute(
            """
            SELECT
                date(observed_at) AS observed_date,
                AVG(CASE WHEN o.currency = 'EUR' THEN o.listed_price END)
                    AS average_price_eur,
                COUNT(DISTINCT CASE
                    WHEN o.listing_status = 'active'
                    THEN o.marketplace_listing_id
                END) AS observed_active_inventory
            FROM marketplace_listing_observations AS o
            JOIN marketplace_listings AS l
              ON l.marketplace_listing_id = o.marketplace_listing_id
            WHERE l.brand_name = ? COLLATE NOCASE
              AND l.model_name = ? COLLATE NOCASE
            GROUP BY date(observed_at)
            ORDER BY date(observed_at)
            """,
            parameters,
        ).fetchall()

    return VehicleAnalysisSnapshot(
        brand_name=normalized_brand,
        model_name=normalized_model,
        active_listing_count=int(stats["active_listing_count"]),
        average_price_eur=_optional_decimal(stats["average_price_eur"]),
        minimum_price_eur=_optional_decimal(stats["minimum_price_eur"]),
        maximum_price_eur=_optional_decimal(stats["maximum_price_eur"]),
        prices_eur=tuple(
            Decimal(str(row["current_price_amount"]))
            for row in distribution_rows
            if row["current_price_amount"] is not None and row["currency"] == "EUR"
        ),
        mileages_km=tuple(
            int(row["mileage_km"])
            for row in distribution_rows
            if row["mileage_km"] is not None
        ),
        registration_years=tuple(
            int(row["registration_year"])
            for row in distribution_rows
            if row["registration_year"] is not None
        ),
        trend=tuple(
            VehicleTrendPoint(
                observed_date=str(row["observed_date"]),
                average_price_eur=_optional_decimal(row["average_price_eur"]),
                observed_active_inventory=int(row["observed_active_inventory"]),
            )
            for row in trend_rows
            if row["observed_date"] is not None
        ),
    )


def load_comparable_vehicle_metadata(
    database_path: str | Path | None = None,
) -> tuple[ComparableVehicleMetadata, ...]:
    """Load canonical peer controls and invalidate cache when SQLite changes."""

    path = resolve_database_path(database_path)
    if not path.is_file():
        raise FileNotFoundError(
            "Project Germania SQLite database was not found at "
            f"'{path}'. A database file will not be created automatically."
        )
    stat = path.stat()
    return _load_comparable_vehicle_metadata_cached(
        str(path), stat.st_mtime_ns, stat.st_size
    )


def clear_comparable_vehicle_metadata_cache() -> None:
    """Clear the peer-control cache for tests or an explicit manual refresh."""

    _load_comparable_vehicle_metadata_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_comparable_vehicle_metadata_cached(
    path_text: str,
    modified_at_ns: int,
    file_size: int,
) -> tuple[ComparableVehicleMetadata, ...]:
    del modified_at_ns, file_size
    with get_connection(path_text) as connection:
        rows = connection.execute("""
            SELECT
                b.canonical_brand,
                b.country_of_origin,
                v.canonical_model,
                v.vehicle_segment,
                v.body_type,
                v.default_powertrain
            FROM vehicles AS v
            JOIN brands AS b ON b.brand_id = v.brand_id
            WHERE v.active = 1 AND b.active = 1
            ORDER BY b.canonical_brand COLLATE NOCASE,
                     v.canonical_model COLLATE NOCASE
            """).fetchall()
    return tuple(
        ComparableVehicleMetadata(
            vehicle_key=f"{row['canonical_brand']} {row['canonical_model']}",
            brand_name=str(row["canonical_brand"]),
            model_name=str(row["canonical_model"]),
            vehicle_segment=_optional_text(row["vehicle_segment"]),
            body_type=_optional_text(row["body_type"]),
            powertrain=_optional_text(row["default_powertrain"]),
            market_attribute=_optional_text(row["country_of_origin"]),
        )
        for row in rows
    )


def load_database_quality(
    database_path: str | Path | None = None,
) -> DatabaseQualitySnapshot:
    """Load current SQLite volume, collection, matching, and completeness data."""

    with get_connection(database_path) as connection:
        listings_count = _table_count(connection, "marketplace_listings")
        active_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM marketplace_listings WHERE active = 1"
            ).fetchone()[0]
        )
        observations_count = _table_count(
            connection, "marketplace_listing_observations"
        )
        price_history_count = _table_count(connection, "marketplace_price_history")
        quality_issue_count = _table_count(connection, "data_quality_issues")
        latest_updated_at = connection.execute(
            "SELECT MAX(last_collected_at) FROM marketplace_listings"
        ).fetchone()[0]
        latest_run_row = connection.execute("""
            SELECT collection_job_id
            FROM collection_batches
            WHERE collection_job_id IS NOT NULL
            ORDER BY COALESCE(completed_at, started_at, created_at) DESC,
                     collection_batch_id DESC
            LIMIT 1
            """).fetchone()
        latest_run_id = (
            str(latest_run_row["collection_job_id"])
            if latest_run_row is not None
            else None
        )
        batch_rows = (
            connection.execute(
                """
                SELECT status, success_count, failure_count, notes
                FROM collection_batches
                WHERE collection_job_id = ?
                ORDER BY collection_batch_id
                """,
                (latest_run_id,),
            ).fetchall()
            if latest_run_id is not None
            else ()
        )
        completeness = _field_completeness(connection, listings_count)

    totals = {
        "requested_pages": 0,
        "succeeded_pages": 0,
        "matched": 0,
        "rejected": 0,
        "low_confidence": 0,
        "import_rejected": 0,
    }
    for row in batch_rows:
        notes = _notes_mapping(row["notes"])
        for key in totals:
            totals[key] += _non_negative_int(notes.get(key))
    task_count = len(batch_rows)
    successful_task_count = sum(row["status"] == "completed" for row in batch_rows)
    return DatabaseQualitySnapshot(
        listings_count=listings_count,
        active_listings_count=active_count,
        observations_count=observations_count,
        price_history_count=price_history_count,
        quality_issue_count=quality_issue_count,
        latest_updated_at=(
            str(latest_updated_at) if latest_updated_at is not None else None
        ),
        latest_run_id=latest_run_id,
        task_count=task_count,
        successful_task_count=successful_task_count,
        task_success_rate_pct=(
            successful_task_count / task_count * 100 if task_count else None
        ),
        requested_pages=totals["requested_pages"],
        succeeded_pages=totals["succeeded_pages"],
        page_success_rate_pct=(
            totals["succeeded_pages"] / totals["requested_pages"] * 100
            if totals["requested_pages"]
            else None
        ),
        matched_count=totals["matched"],
        rejected_count=totals["rejected"],
        low_confidence_count=totals["low_confidence"],
        import_rejected_count=totals["import_rejected"],
        field_completeness_pct=completeness,
    )


def _listing_result(row: sqlite3.Row) -> ListingSearchResult:
    price = row["current_price_amount"]
    return ListingSearchResult(
        external_listing_id=str(row["external_listing_id"]),
        brand_name=row["brand_name"],
        model_name=row["model_name"],
        title=row["title"],
        current_price_amount=Decimal(str(price)) if price is not None else None,
        currency=str(row["currency"]),
        mileage_km=row["mileage_km"],
        fuel_type=row["fuel_type"],
        registration_year=row["registration_year"],
        seller_city=row["seller_city"],
        active=bool(row["active"]),
        last_collected_at=row["last_collected_at"],
        listing_url=row["listing_url"],
    )


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def _table_count(connection: sqlite3.Connection, table_name: str) -> int:
    allowed = {
        "marketplace_listings",
        "marketplace_listing_observations",
        "marketplace_price_history",
        "data_quality_issues",
    }
    if table_name not in allowed:
        raise ValueError("unsupported table name")
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _field_completeness(
    connection: sqlite3.Connection,
    denominator: int,
) -> dict[str, float | None]:
    fields = {
        "品牌": "brand_name",
        "车型": "model_name",
        "挂牌价": "current_price_amount",
        "货币": "currency",
        "里程": "mileage_km",
        "注册年份": "registration_year",
        "来源链接": "listing_url",
        "最后采集时间": "last_collected_at",
    }
    if denominator == 0:
        return {label: None for label in fields}
    row = connection.execute(
        "SELECT "
        + ", ".join(
            f"SUM(CASE WHEN {column} IS NOT NULL "
            f"AND trim(CAST({column} AS TEXT)) <> '' THEN 1 ELSE 0 END) AS f{index}"
            for index, column in enumerate(fields.values())
        )
        + " FROM marketplace_listings"
    ).fetchone()
    return {
        label: int(row[f"f{index}"]) / denominator * 100
        for index, label in enumerate(fields)
    }


def _notes_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _non_negative_int(value: object) -> int:
    is_valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if is_valid else 0


def _optional_non_negative_decimal(
    value: Decimal | int | None,
    field: str,
) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative number")
    try:
        result = Decimal(value)
    except (ArithmeticError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return result


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
