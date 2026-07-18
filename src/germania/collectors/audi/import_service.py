"""Import Audi Germany official price records through the shared service."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.audi.parser import AudiOfficialPriceParser
from germania.collectors.volkswagen.import_service import (
    VolkswagenOfficialPriceImportResult,
    VolkswagenOfficialPriceImportService,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord

AudiOfficialPriceImportResult = VolkswagenOfficialPriceImportResult


class AudiOfficialPriceImportService:
    """Import parsed Audi Germany official prices using the shared repository flow."""

    def __init__(
        self,
        session: Session,
        *,
        parser: AudiOfficialPriceParser | None = None,
    ) -> None:
        self.parser = parser or AudiOfficialPriceParser()
        self._shared_service = VolkswagenOfficialPriceImportService(session)

    def import_html(
        self,
        path: Path | str,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> AudiOfficialPriceImportResult:
        """Parse and import one local Audi Germany HTML fixture."""

        html = Path(path).read_text(encoding="utf-8")
        return self.import_records(
            self.parser.parse_price_page(
                html,
                source_url=source_url,
                collected_at=collected_at,
            )
        )

    def import_records(
        self,
        records: Iterable[OfficialPriceRecord],
    ) -> AudiOfficialPriceImportResult:
        """Import parsed official price records through the shared service."""

        return self._shared_service.import_records(records)
