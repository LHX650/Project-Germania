"""Read-only SQLite marketplace exports to CSV and Excel."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from germania.db.models import DataSource, MarketplaceListing, MarketplacePriceHistory
from germania.utils.workbook import (
    add_table_sheet,
    create_report_workbook,
    save_report_workbook,
)

LISTING_HEADERS = (
    "marketplace_listing_id",
    "source_id",
    "external_listing_id",
    "brand_name",
    "model_name",
    "variant_name",
    "title",
    "current_price_amount",
    "currency",
    "registration_year",
    "fuel_type",
    "transmission",
    "power_kw",
    "vehicle_condition",
    "body_type",
    "color",
    "mileage_km",
    "seller_type",
    "seller_name",
    "country_code",
    "state",
    "seller_city",
    "seller_postcode",
    "listing_url",
    "first_seen_at",
    "last_seen_at",
    "last_collected_at",
    "source_updated_at",
    "active",
    "created_at",
    "updated_at",
)
PRICE_HISTORY_HEADERS = (
    "marketplace_price_history_id",
    "marketplace_listing_id",
    "source_id",
    "external_listing_id",
    "brand_name",
    "model_name",
    "price_amount",
    "currency",
    "observed_at",
    "collected_at",
    "source_updated_at",
    "listing_url",
    "created_at",
)
BRAND_SUMMARY_HEADERS = (
    "brand_name",
    "listing_count",
    "average_price",
    "minimum_price",
    "maximum_price",
    "average_mileage",
    "latest_update_time",
)
VEHICLE_SUMMARY_HEADERS = (
    "brand_name",
    "model_name",
    "listing_count",
    "average_price",
    "minimum_price",
    "maximum_price",
    "average_mileage",
    "latest_update_time",
)
COLLECTION_SUMMARY_HEADERS = ("metric", "value")


@dataclass(frozen=True)
class MarketplaceExportResult:
    """Paths and source row counts for one export run."""

    workbook_path: Path
    csv_paths: tuple[Path, ...]
    listing_count: int
    price_history_count: int
    brand_count: int
    vehicle_count: int


def export_marketplace_data(
    session: Session,
    output_dir: Path | str = Path("exports"),
) -> MarketplaceExportResult:
    """Export marketplace tables and summaries without changing the database."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    listings = _listing_rows(session)
    price_history = _price_history_rows(session)
    brand_summary = _brand_summary_rows(session)
    vehicle_summary = _vehicle_summary_rows(session)
    collection_summary = _collection_summary_rows(
        listings,
        price_history,
        brand_summary,
        vehicle_summary,
    )

    csv_specs = (
        ("listings.csv", LISTING_HEADERS, listings),
        ("price_history.csv", PRICE_HISTORY_HEADERS, price_history),
        ("brand_summary.csv", BRAND_SUMMARY_HEADERS, brand_summary),
        ("vehicle_summary.csv", VEHICLE_SUMMARY_HEADERS, vehicle_summary),
    )
    csv_paths: list[Path] = []
    for filename, headers, rows in csv_specs:
        path = destination / filename
        _write_csv(path, headers, rows)
        csv_paths.append(path)

    workbook = create_report_workbook()
    add_table_sheet(
        workbook,
        title="Listings",
        headers=LISTING_HEADERS,
        rows=listings,
        table_name="ListingsTable",
    )
    add_table_sheet(
        workbook,
        title="Price_History",
        headers=PRICE_HISTORY_HEADERS,
        rows=price_history,
        table_name="PriceHistoryTable",
    )
    add_table_sheet(
        workbook,
        title="Brand_Summary",
        headers=BRAND_SUMMARY_HEADERS,
        rows=brand_summary,
        table_name="BrandSummaryTable",
    )
    add_table_sheet(
        workbook,
        title="Vehicle_Summary",
        headers=VEHICLE_SUMMARY_HEADERS,
        rows=vehicle_summary,
        table_name="VehicleSummaryTable",
    )
    add_table_sheet(
        workbook,
        title="Collection_Summary",
        headers=COLLECTION_SUMMARY_HEADERS,
        rows=collection_summary,
        table_name="CollectionSummaryTable",
    )
    workbook_path = destination / "project_germania_marketplace.xlsx"
    save_report_workbook(workbook, workbook_path)

    return MarketplaceExportResult(
        workbook_path=workbook_path,
        csv_paths=tuple(csv_paths),
        listing_count=len(listings),
        price_history_count=len(price_history),
        brand_count=len(brand_summary),
        vehicle_count=len(vehicle_summary),
    )


def _listing_rows(session: Session) -> list[tuple[Any, ...]]:
    statement = (
        select(
            MarketplaceListing.marketplace_listing_id,
            DataSource.source_id,
            MarketplaceListing.external_listing_id,
            MarketplaceListing.brand_name,
            MarketplaceListing.model_name,
            MarketplaceListing.variant_name,
            MarketplaceListing.title,
            MarketplaceListing.current_price_amount,
            MarketplaceListing.currency,
            MarketplaceListing.registration_year,
            MarketplaceListing.fuel_type,
            MarketplaceListing.transmission,
            MarketplaceListing.power_kw,
            MarketplaceListing.vehicle_condition,
            MarketplaceListing.body_type,
            MarketplaceListing.color,
            MarketplaceListing.mileage_km,
            MarketplaceListing.seller_type,
            MarketplaceListing.seller_name,
            MarketplaceListing.country_code,
            MarketplaceListing.state,
            MarketplaceListing.seller_city,
            MarketplaceListing.seller_postcode,
            MarketplaceListing.listing_url,
            MarketplaceListing.first_seen_at,
            MarketplaceListing.last_seen_at,
            MarketplaceListing.last_collected_at,
            MarketplaceListing.source_updated_at,
            MarketplaceListing.active,
            MarketplaceListing.created_at,
            MarketplaceListing.updated_at,
        )
        .join(
            DataSource, MarketplaceListing.data_source_id == DataSource.data_source_id
        )
        .order_by(MarketplaceListing.marketplace_listing_id)
    )
    return [tuple(row) for row in session.execute(statement).all()]


def _price_history_rows(session: Session) -> list[tuple[Any, ...]]:
    statement = (
        select(
            MarketplacePriceHistory.marketplace_price_history_id,
            MarketplacePriceHistory.marketplace_listing_id,
            DataSource.source_id,
            MarketplaceListing.external_listing_id,
            MarketplaceListing.brand_name,
            MarketplaceListing.model_name,
            MarketplacePriceHistory.price_amount,
            MarketplacePriceHistory.currency,
            MarketplacePriceHistory.observed_at,
            MarketplacePriceHistory.collected_at,
            MarketplacePriceHistory.source_updated_at,
            MarketplacePriceHistory.listing_url,
            MarketplacePriceHistory.created_at,
        )
        .join(
            MarketplaceListing,
            MarketplacePriceHistory.marketplace_listing_id
            == MarketplaceListing.marketplace_listing_id,
        )
        .join(
            DataSource, MarketplaceListing.data_source_id == DataSource.data_source_id
        )
        .order_by(MarketplacePriceHistory.marketplace_price_history_id)
    )
    return [tuple(row) for row in session.execute(statement).all()]


def _brand_summary_rows(session: Session) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in session.execute(
            select(
                MarketplaceListing.brand_name,
                func.count(MarketplaceListing.marketplace_listing_id),
                func.avg(MarketplaceListing.current_price_amount),
                func.min(MarketplaceListing.current_price_amount),
                func.max(MarketplaceListing.current_price_amount),
                func.avg(MarketplaceListing.mileage_km),
                func.max(MarketplaceListing.last_collected_at),
            )
            .group_by(MarketplaceListing.brand_name)
            .order_by(MarketplaceListing.brand_name)
        ).all()
    ]


def _vehicle_summary_rows(session: Session) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in session.execute(
            select(
                MarketplaceListing.brand_name,
                MarketplaceListing.model_name,
                func.count(MarketplaceListing.marketplace_listing_id),
                func.avg(MarketplaceListing.current_price_amount),
                func.min(MarketplaceListing.current_price_amount),
                func.max(MarketplaceListing.current_price_amount),
                func.avg(MarketplaceListing.mileage_km),
                func.max(MarketplaceListing.last_collected_at),
            )
            .group_by(MarketplaceListing.brand_name, MarketplaceListing.model_name)
            .order_by(MarketplaceListing.brand_name, MarketplaceListing.model_name)
        ).all()
    ]


def _collection_summary_rows(
    listings: list[tuple[Any, ...]],
    price_history: list[tuple[Any, ...]],
    brand_summary: list[tuple[Any, ...]],
    vehicle_summary: list[tuple[Any, ...]],
) -> list[tuple[str, Any]]:
    collected_values = [row[26] for row in listings if row[26] is not None]
    listings_with_history = len({row[1] for row in price_history})
    return [
        ("marketplace_listings", len(listings)),
        ("price_history", len(price_history)),
        ("brands", len(brand_summary)),
        ("vehicles", len(vehicle_summary)),
        ("listings_with_price_history", listings_with_history),
        ("listings_without_price_history", len(listings) - listings_with_history),
        ("earliest_collection_time", min(collected_values, default=None)),
        ("latest_collection_time", max(collected_values, default=None)),
    ]


def _write_csv(
    path: Path,
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
