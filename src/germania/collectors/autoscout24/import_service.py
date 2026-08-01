"""Import local AutoScout24 HTML fixtures into marketplace tables."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.collectors.autoscout24.config import AUTOSCOUT24_DE_SOURCE_ID
from germania.collectors.autoscout24.parser import AutoScout24ListingParser
from germania.collectors.marketplace import MarketplaceListingRecord
from germania.config import UNKNOWN, normalize_brand, normalize_model
from germania.db.models import MarketplaceListingObservation, Vehicle
from germania.db.repositories import (
    BaseRepository,
    BrandRepository,
    DataSourceRepository,
    MarketplaceListingRepository,
    VehicleRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoScout24ImportResult:
    """Summary counts for one local AutoScout24 fixture import."""

    total: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    price_history_inserted: int
    observations_inserted: int = 0


def combine_import_results(
    results: Iterable[AutoScout24ImportResult],
) -> AutoScout24ImportResult:
    """Combine multiple AutoScout24 import summaries."""

    total = 0
    inserted = 0
    updated = 0
    skipped = 0
    rejected = 0
    price_history_inserted = 0
    observations_inserted = 0
    for result in results:
        total += result.total
        inserted += result.inserted
        updated += result.updated
        skipped += result.skipped
        rejected += result.rejected
        price_history_inserted += result.price_history_inserted
        observations_inserted += result.observations_inserted

    return AutoScout24ImportResult(
        total=total,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        rejected=rejected,
        price_history_inserted=price_history_inserted,
        observations_inserted=observations_inserted,
    )


class AutoScout24ListingImportService:
    """Import normalized AutoScout24 fixture records through repositories."""

    def __init__(
        self,
        session: Session,
        *,
        parser: AutoScout24ListingParser | None = None,
    ) -> None:
        self.session = session
        self.parser = parser or AutoScout24ListingParser()
        self.source_repository = DataSourceRepository(session)
        self.brand_repository = BrandRepository(session)
        self.vehicle_repository = VehicleRepository(session)
        self.listing_repository = MarketplaceListingRepository(session)

    def import_html(
        self,
        path: Path | str,
        *,
        collected_at: datetime | None = None,
    ) -> AutoScout24ImportResult:
        """Parse and import one local AutoScout24 HTML document."""

        html = Path(path).read_text(encoding="utf-8")
        records = self.parser.parse_marketplace_listing_page(
            html,
            collected_at=collected_at,
        )
        return self.import_records(records)

    def dry_run_html(
        self,
        path: Path | str,
        *,
        collected_at: datetime | None = None,
    ) -> AutoScout24ImportResult:
        """Predict one HTML import and roll back all marketplace writes."""

        html = Path(path).read_text(encoding="utf-8")
        records = self.parser.parse_marketplace_listing_page(
            html,
            collected_at=collected_at,
        )
        return self.dry_run_records(records)

    def dry_run_records(
        self,
        records: Iterable[MarketplaceListingRecord],
    ) -> AutoScout24ImportResult:
        """Predict repository results inside a rolled-back database savepoint."""

        transaction = self.session.begin_nested()
        try:
            return self.import_records(records)
        finally:
            if transaction.is_active:
                transaction.rollback()
            self.session.expire_all()

    def import_records(
        self,
        records: Iterable[MarketplaceListingRecord],
        *,
        collection_batch_id: int | None = None,
    ) -> AutoScout24ImportResult:
        """Import parsed listing records without creating vehicle master data."""

        inserted = 0
        updated = 0
        skipped = 0
        rejected = 0
        price_history_inserted = 0
        observations_inserted = 0
        total = 0

        for record in records:
            total += 1
            vehicle = self._resolve_vehicle(record)
            if vehicle is None or not _has_required_values(record):
                rejected += 1
                continue

            canonical_record = replace(
                record,
                brand_name=vehicle.brand.canonical_brand,
                model_name=vehicle.canonical_model,
            )
            upsert_result = self.listing_repository.upsert_listing_record(
                canonical_record,
                vehicle_id=vehicle.vehicle_id,
            )
            if upsert_result.price_history_created:
                price_history_inserted += 1
            if collection_batch_id is not None and self._add_observation_if_missing(
                upsert_result.listing.marketplace_listing_id,
                record,
                collection_batch_id=collection_batch_id,
            ):
                observations_inserted += 1
            if upsert_result.created:
                inserted += 1
            elif upsert_result.updated or upsert_result.price_history_created:
                updated += 1
            else:
                skipped += 1

        result = AutoScout24ImportResult(
            total=total,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            rejected=rejected,
            price_history_inserted=price_history_inserted,
            observations_inserted=observations_inserted,
        )
        logger.info(
            "Imported AutoScout24 fixture: total=%s inserted=%s updated=%s "
            "skipped=%s rejected=%s price_history_inserted=%s "
            "observations_inserted=%s",
            result.total,
            result.inserted,
            result.updated,
            result.skipped,
            result.rejected,
            result.price_history_inserted,
            result.observations_inserted,
        )
        return result

    def _add_observation_if_missing(
        self,
        marketplace_listing_id: int,
        record: MarketplaceListingRecord,
        *,
        collection_batch_id: int,
    ) -> bool:
        observed_at = _to_aware_utc(record.collected_at)
        existing = self.session.scalar(
            select(MarketplaceListingObservation).where(
                MarketplaceListingObservation.marketplace_listing_id
                == marketplace_listing_id,
                MarketplaceListingObservation.observed_at == observed_at,
            )
        )
        if existing is not None:
            return False

        BaseRepository(self.session, MarketplaceListingObservation).add(
            MarketplaceListingObservation(
                marketplace_listing_id=marketplace_listing_id,
                collection_batch_id=collection_batch_id,
                listed_price=record.price_amount,
                currency=record.currency,
                price_includes_vat=None,
                observed_at=observed_at,
                collected_at=record.collected_at,
                listing_status="active",
                mileage_km=record.mileage_km,
                source_url=record.listing_url,
                data_quality_status="valid",
                validation_status="passed",
                duplicate_key=(
                    f"{record.source_id}:{record.external_listing_id}:"
                    f"{observed_at.isoformat()}"
                ),
                notes=None,
            )
        )
        return True

    def _resolve_vehicle(self, record: MarketplaceListingRecord) -> Vehicle | None:
        if record.source_id != AUTOSCOUT24_DE_SOURCE_ID:
            return None
        if self.source_repository.get_by_source_id(record.source_id) is None:
            return None

        canonical_brand = normalize_brand(record.brand_name)
        canonical_model = normalize_model(record.model_name)
        if canonical_brand == UNKNOWN or canonical_model == UNKNOWN:
            return None

        brand = self.brand_repository.get_by_name(canonical_brand)
        if brand is None:
            return None
        return self.vehicle_repository.get_by_code(
            brand.brand_id,
            canonical_model,
        )


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _has_required_values(record: MarketplaceListingRecord) -> bool:
    return bool(
        record.external_listing_id.strip()
        and record.price_amount is not None
        and record.price_amount > 0
        and record.currency == "EUR"
    )
