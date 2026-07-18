"""Import Volkswagen Germany official price records into the database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.volkswagen.models import OfficialPriceRecord
from germania.collectors.volkswagen.parser import VolkswagenOfficialPriceParser
from germania.db.models import VehicleVariant
from germania.db.repositories.brand import BrandRepository
from germania.db.repositories.price import OfficialPriceRepository
from germania.db.repositories.source import DataSourceRepository
from germania.db.repositories.variant import VariantRepository
from germania.db.repositories.vehicle import VehicleRepository


@dataclass(frozen=True)
class VolkswagenOfficialPriceImportResult:
    """Summary counts for one Volkswagen official price import run."""

    total: int
    inserted: int
    updated: int
    skipped: int
    rejected: int


class VolkswagenOfficialPriceImportService:
    """Import parsed Volkswagen Germany official prices through repositories."""

    def __init__(
        self,
        session: Session,
        *,
        parser: VolkswagenOfficialPriceParser | None = None,
    ) -> None:
        self.parser = parser or VolkswagenOfficialPriceParser()
        self.source_repository = DataSourceRepository(session)
        self.brand_repository = BrandRepository(session)
        self.vehicle_repository = VehicleRepository(session)
        self.variant_repository = VariantRepository(session)
        self.price_repository = OfficialPriceRepository(session)

    def import_html(
        self,
        path: Path | str,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> VolkswagenOfficialPriceImportResult:
        """Parse and import one local Volkswagen Germany HTML fixture."""

        html = Path(path).read_text(encoding="utf-8")
        records = self.parser.parse_price_page(
            html,
            source_url=source_url,
            collected_at=collected_at,
        )
        return self.import_records(records)

    def import_records(
        self,
        records: Iterable[OfficialPriceRecord],
    ) -> VolkswagenOfficialPriceImportResult:
        """Import parsed official price records in bulk."""

        inserted = 0
        updated = 0
        skipped = 0
        rejected = 0
        total = 0

        for record in records:
            total += 1
            variant = self._resolve_variant(record)
            if variant is None or not _has_required_price_values(record):
                rejected += 1
                continue

            upsert_result = self.price_repository.upsert_official_price_record(
                record,
                vehicle_variant_id=variant.vehicle_variant_id,
            )
            if upsert_result.created:
                inserted += 1
            elif upsert_result.updated:
                updated += 1
            else:
                skipped += 1

        return VolkswagenOfficialPriceImportResult(
            total=total,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            rejected=rejected,
        )

    def _resolve_variant(self, record: OfficialPriceRecord) -> VehicleVariant | None:
        source = self.source_repository.get_by_source_id(record.source_id)
        if source is None:
            return None

        if record.canonical_brand_name is None or record.canonical_model_name is None:
            return None
        brand = self.brand_repository.get_by_name(record.canonical_brand_name)
        if brand is None:
            return None

        vehicle = self.vehicle_repository.get_by_code(
            brand.brand_id,
            record.canonical_model_name,
        )
        if vehicle is None:
            return None

        if record.raw_variant_name is None:
            return None
        variants = self.variant_repository.list_by_vehicle(
            vehicle.vehicle_id,
            active=True,
        )
        for variant in variants:
            if record.raw_variant_name in {
                variant.trim_name,
                variant.variant_name,
                variant.edition_name,
            }:
                return variant
        return None


def _has_required_price_values(record: OfficialPriceRecord) -> bool:
    return (
        record.price_eur is not None
        and record.original_currency == "EUR"
        and record.valid_date is not None
    )
