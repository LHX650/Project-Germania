"""Read-only data quality checks for marketplace listings."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl.styles import Alignment
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from germania.db.models import (
    Brand,
    MarketplaceListing,
    MarketplacePriceHistory,
    Vehicle,
)
from germania.utils.workbook import (
    add_table_sheet,
    create_report_workbook,
    save_report_workbook,
)

MIN_EXPECTED_PRICE = Decimal("1000")
MAX_EXPECTED_PRICE = Decimal("250000")
MAX_EXPECTED_MILEAGE_KM = 500_000

_QUALITY_FIELDS = (
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
    "mileage_km",
    "seller_type",
    "seller_name",
    "country_code",
    "seller_city",
    "seller_postcode",
    "listing_url",
    "last_collected_at",
)


@dataclass(frozen=True)
class MarketplaceQualityResult:
    """Summary and output path for one quality-report run."""

    workbook_path: Path
    total_listings: int
    overall_completeness_rate: float
    total_missing_values: int
    duplicate_external_id_groups: int
    listings_without_price_history: int
    price_anomalies: int
    mileage_anomalies: int
    brand_model_inconsistencies: int


def create_marketplace_quality_report(
    session: Session,
    output_dir: Path | str = Path("exports"),
) -> MarketplaceQualityResult:
    """Evaluate marketplace data and write an auditable Excel report."""

    listings = list(
        session.scalars(
            select(MarketplaceListing).order_by(
                MarketplaceListing.marketplace_listing_id
            )
        )
    )
    completeness, missing_values = _field_quality_rows(listings)
    duplicates = _duplicate_rows(session)
    missing_history = _missing_history_rows(session)
    price_anomalies = _price_anomaly_rows(listings)
    mileage_anomalies = _mileage_anomaly_rows(listings)
    consistency_issues = _brand_model_consistency_rows(session)

    total_cells = len(listings) * len(_QUALITY_FIELDS)
    total_missing = sum(row[2] for row in completeness)
    completeness_rate = (
        (total_cells - total_missing) / total_cells if total_cells else 1.0
    )
    summary_rows = [
        ("total_listings", len(listings)),
        ("checked_fields", len(_QUALITY_FIELDS)),
        ("overall_completeness_rate", completeness_rate),
        ("total_missing_values", total_missing),
        ("duplicate_external_id_groups", len(duplicates)),
        ("listings_without_price_history", len(missing_history)),
        ("price_anomalies", len(price_anomalies)),
        ("mileage_anomalies", len(mileage_anomalies)),
        ("brand_model_inconsistencies", len(consistency_issues)),
        ("minimum_expected_price_eur", MIN_EXPECTED_PRICE),
        ("maximum_expected_price_eur", MAX_EXPECTED_PRICE),
        ("maximum_expected_mileage_km", MAX_EXPECTED_MILEAGE_KM),
    ]

    workbook = create_report_workbook()
    quality_summary_sheet = add_table_sheet(
        workbook,
        title="Quality_Summary",
        headers=("metric", "value"),
        rows=summary_rows,
        table_name="QualitySummaryTable",
    )
    quality_summary_sheet["B4"].number_format = "0.0%"
    missing_values_sheet = add_table_sheet(
        workbook,
        title="Field_Completeness",
        headers=("field_name", "present_count", "missing_count", "completeness_rate"),
        rows=completeness,
        table_name="FieldCompletenessTable",
    )
    add_table_sheet(
        workbook,
        title="Missing_Values",
        headers=("field_name", "missing_count", "sample_external_listing_ids"),
        rows=missing_values,
        table_name="MissingValuesTable",
    )
    for cell in missing_values_sheet["C"][1:]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if cell.value:
            missing_values_sheet.row_dimensions[cell.row].height = 45
    add_table_sheet(
        workbook,
        title="Duplicate_IDs",
        headers=("external_listing_id", "listing_count", "source_count"),
        rows=duplicates,
        table_name="DuplicateIdsTable",
    )
    add_table_sheet(
        workbook,
        title="Missing_History",
        headers=(
            "marketplace_listing_id",
            "external_listing_id",
            "brand_name",
            "model_name",
        ),
        rows=missing_history,
        table_name="MissingHistoryTable",
    )
    add_table_sheet(
        workbook,
        title="Price_Anomalies",
        headers=(
            "marketplace_listing_id",
            "external_listing_id",
            "brand_name",
            "model_name",
            "current_price_amount",
            "reason",
        ),
        rows=price_anomalies,
        table_name="PriceAnomaliesTable",
    )
    add_table_sheet(
        workbook,
        title="Mileage_Anomalies",
        headers=(
            "marketplace_listing_id",
            "external_listing_id",
            "brand_name",
            "model_name",
            "mileage_km",
            "reason",
        ),
        rows=mileage_anomalies,
        table_name="MileageAnomaliesTable",
    )
    add_table_sheet(
        workbook,
        title="Brand_Model_Check",
        headers=(
            "marketplace_listing_id",
            "external_listing_id",
            "listing_brand",
            "listing_model",
            "canonical_brand",
            "canonical_model",
            "reason",
        ),
        rows=consistency_issues,
        table_name="BrandModelCheckTable",
    )

    workbook_path = Path(output_dir) / "project_germania_quality_report.xlsx"
    save_report_workbook(workbook, workbook_path)
    return MarketplaceQualityResult(
        workbook_path=workbook_path,
        total_listings=len(listings),
        overall_completeness_rate=completeness_rate,
        total_missing_values=total_missing,
        duplicate_external_id_groups=len(duplicates),
        listings_without_price_history=len(missing_history),
        price_anomalies=len(price_anomalies),
        mileage_anomalies=len(mileage_anomalies),
        brand_model_inconsistencies=len(consistency_issues),
    )


def _field_quality_rows(
    listings: list[MarketplaceListing],
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    completeness: list[tuple[Any, ...]] = []
    missing_values: list[tuple[Any, ...]] = []
    total = len(listings)
    for field_name in _QUALITY_FIELDS:
        missing = [
            listing for listing in listings if _is_missing(getattr(listing, field_name))
        ]
        missing_count = len(missing)
        completeness.append(
            (
                field_name,
                total - missing_count,
                missing_count,
                (total - missing_count) / total if total else 1.0,
            )
        )
        missing_values.append(
            (
                field_name,
                missing_count,
                missing[0].external_listing_id if missing else "",
            )
        )
    return completeness, missing_values


def _duplicate_rows(session: Session) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in session.execute(
            select(
                MarketplaceListing.external_listing_id,
                func.count(MarketplaceListing.marketplace_listing_id),
                func.count(func.distinct(MarketplaceListing.data_source_id)),
            )
            .group_by(MarketplaceListing.external_listing_id)
            .having(func.count(MarketplaceListing.marketplace_listing_id) > 1)
            .order_by(MarketplaceListing.external_listing_id)
        ).all()
    ]


def _missing_history_rows(session: Session) -> list[tuple[Any, ...]]:
    history_count = func.count(MarketplacePriceHistory.marketplace_price_history_id)
    return [
        tuple(row[:4])
        for row in session.execute(
            select(
                MarketplaceListing.marketplace_listing_id,
                MarketplaceListing.external_listing_id,
                MarketplaceListing.brand_name,
                MarketplaceListing.model_name,
                history_count,
            )
            .outerjoin(
                MarketplacePriceHistory,
                MarketplaceListing.marketplace_listing_id
                == MarketplacePriceHistory.marketplace_listing_id,
            )
            .group_by(MarketplaceListing.marketplace_listing_id)
            .having(history_count == 0)
            .order_by(MarketplaceListing.marketplace_listing_id)
        ).all()
    ]


def _price_anomaly_rows(
    listings: list[MarketplaceListing],
) -> list[tuple[Any, ...]]:
    output: list[tuple[Any, ...]] = []
    for listing in listings:
        price = listing.current_price_amount
        reason = None
        if price is not None and price < MIN_EXPECTED_PRICE:
            reason = f"price below EUR {MIN_EXPECTED_PRICE}"
        elif price is not None and price > MAX_EXPECTED_PRICE:
            reason = f"price above EUR {MAX_EXPECTED_PRICE}"
        if reason:
            output.append(
                (
                    listing.marketplace_listing_id,
                    listing.external_listing_id,
                    listing.brand_name,
                    listing.model_name,
                    price,
                    reason,
                )
            )
    return output


def _mileage_anomaly_rows(
    listings: list[MarketplaceListing],
) -> list[tuple[Any, ...]]:
    output: list[tuple[Any, ...]] = []
    for listing in listings:
        mileage = listing.mileage_km
        reason = None
        if mileage is not None and mileage < 0:
            reason = "negative mileage"
        elif mileage is not None and mileage > MAX_EXPECTED_MILEAGE_KM:
            reason = f"mileage above {MAX_EXPECTED_MILEAGE_KM} km"
        if reason:
            output.append(
                (
                    listing.marketplace_listing_id,
                    listing.external_listing_id,
                    listing.brand_name,
                    listing.model_name,
                    mileage,
                    reason,
                )
            )
    return output


def _brand_model_consistency_rows(session: Session) -> list[tuple[Any, ...]]:
    rows = session.execute(
        select(
            MarketplaceListing.marketplace_listing_id,
            MarketplaceListing.external_listing_id,
            MarketplaceListing.brand_name,
            MarketplaceListing.model_name,
            Brand.canonical_brand,
            Vehicle.canonical_model,
        )
        .outerjoin(Vehicle, MarketplaceListing.vehicle_id == Vehicle.vehicle_id)
        .outerjoin(Brand, Vehicle.brand_id == Brand.brand_id)
        .order_by(MarketplaceListing.marketplace_listing_id)
    ).all()
    output: list[tuple[Any, ...]] = []
    for row in rows:
        reason = None
        if row[4] is None or row[5] is None:
            reason = "missing canonical vehicle relationship"
        elif row[2] != row[4] or row[3] != row[5]:
            reason = "listing brand/model differs from canonical vehicle"
        if reason:
            output.append((*tuple(row), reason))
    return output


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
