"""Import parsed KBA registration records into the database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.kba.models import RegistrationRecord
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


class KBAImportService:
    """Import KBA FZ10 parser output through registration repositories."""

    def __init__(
        self,
        session: Session,
        *,
        parser: KBAXlsxParser | None = None,
    ) -> None:
        self.parser = parser or KBAXlsxParser()
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
        total = 0

        for record in records:
            total += 1
            resolved = self._resolve_vehicle(record)
            if resolved is None:
                skipped += 1
                continue

            brand_id, vehicle_id = resolved
            upsert_result = self.registration_repository.upsert_kba_record(
                record,
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
        )

    def _resolve_vehicle(self, record: RegistrationRecord) -> tuple[int, int] | None:
        brand = self.brand_repository.get_by_name(record.brand)
        if brand is None:
            return None

        vehicle = self.vehicle_repository.get_by_code(
            brand.brand_id,
            record.model_series,
        )
        if vehicle is None:
            return None

        return brand.brand_id, vehicle.vehicle_id
