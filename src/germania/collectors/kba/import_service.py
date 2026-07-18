"""Import parsed KBA registration records into the database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.kba.models import RegistrationRecord
from germania.collectors.kba.name_mapping import KBANameMapping
from germania.collectors.kba.parser import KBAXlsxParser
from germania.db.repositories import (
    BrandRepository,
    RegistrationObservationRepository,
    VehicleRepository,
)


@dataclass(frozen=True)
class KBAImportResult:
    """Summary counts for one KBA import run."""

    inserted: int
    updated: int
    skipped: int
    total: int
    matched: int = 0
    rejected: int = 0


class KBAImportService:
    """Import KBA FZ10 parser output through registration repositories."""

    def __init__(
        self,
        session: Session,
        *,
        parser: KBAXlsxParser | None = None,
        name_mapping: KBANameMapping | None = None,
    ) -> None:
        self.parser = parser or KBAXlsxParser()
        self.name_mapping = name_mapping or KBANameMapping.load()
        self.brand_repository = BrandRepository(session)
        self.vehicle_repository = VehicleRepository(session)
        self.registration_repository = RegistrationObservationRepository(session)

    def import_xlsx(
        self,
        path: Path | str,
        *,
        year: int | None = None,
        month: int | None = None,
        source_url: str | None = None,
        collected_at: datetime | None = None,
        registration_scope: str = "Germany",
        country_code: str = "DE",
    ) -> KBAImportResult:
        """Parse and import one local KBA FZ10 XLSX workbook."""

        records = self.parser.parse_file(
            path,
            year=year,
            month=month,
            source_url=source_url,
            collected_at=collected_at,
        )
        return self.import_records(
            records,
            registration_scope=registration_scope,
            country_code=country_code,
        )

    def import_records(
        self,
        records: Iterable[RegistrationRecord],
        *,
        registration_scope: str = "Germany",
        country_code: str = "DE",
    ) -> KBAImportResult:
        """Import parsed KBA registration records in bulk."""

        inserted = 0
        updated = 0
        skipped = 0
        matched = 0
        rejected = 0
        total = 0

        for record in records:
            total += 1
            if self._is_rejected_by_mapping(record):
                rejected += 1
                continue

            resolved = self._resolve_vehicle(record)
            if resolved is None:
                skipped += 1
                continue

            brand_id, vehicle_id, mapped_record = resolved
            matched += 1
            upsert_result = self.registration_repository.upsert_kba_record(
                mapped_record,
                brand_id=brand_id,
                vehicle_id=vehicle_id,
                registration_scope=registration_scope,
                country_code=country_code,
            )
            if upsert_result.created:
                inserted += 1
            elif upsert_result.updated:
                updated += 1
            else:
                skipped += 1

        return KBAImportResult(
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            total=total,
            matched=matched,
            rejected=rejected,
        )

    def _resolve_vehicle(
        self,
        record: RegistrationRecord,
    ) -> tuple[int, int, RegistrationRecord] | None:
        raw_brand = _standardize_name(record.brand)
        raw_model = _standardize_name(record.model_series)

        canonical_brand = self.name_mapping.normalize_brand(raw_brand)
        brand = self.brand_repository.get_by_name(canonical_brand)
        if brand is None:
            return None

        mapped_brand, canonical_model = self.name_mapping.normalize_vehicle(
            raw_brand,
            raw_model,
        )
        if mapped_brand != canonical_brand:
            return None

        vehicle = self.vehicle_repository.get_by_code(
            brand.brand_id,
            canonical_model,
        )
        if vehicle is None:
            return None

        mapped_record = RegistrationRecord(
            source_id=record.source_id,
            year=record.year,
            month=record.month,
            brand=canonical_brand,
            model_series=canonical_model,
            registrations=record.registrations,
            fuel_type=record.fuel_type,
            market_share=record.market_share,
            source_url=record.source_url,
            collected_at=record.collected_at,
        )
        return brand.brand_id, vehicle.vehicle_id, mapped_record

    def _is_rejected_by_mapping(self, record: RegistrationRecord) -> bool:
        return self.name_mapping.is_rejected_vehicle(
            _standardize_name(record.brand),
            _standardize_name(record.model_series),
        )


def _standardize_name(value: str) -> str:
    return " ".join(value.strip().split())
