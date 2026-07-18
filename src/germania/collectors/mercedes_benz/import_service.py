"""Import Mercedes-Benz Germany official price records through the shared service."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.mercedes_benz.parser import (
    MercedesBenzOfficialPriceParser,
)
from germania.collectors.volkswagen.import_service import (
    VolkswagenOfficialPriceImportResult,
    VolkswagenOfficialPriceImportService,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord

MercedesBenzOfficialPriceImportResult = VolkswagenOfficialPriceImportResult


class MercedesBenzOfficialPriceImportService:
    """Import parsed Mercedes-Benz prices using the shared repository flow."""

    def __init__(
        self,
        session: Session,
        *,
        parser: MercedesBenzOfficialPriceParser | None = None,
    ) -> None:
        self.parser = parser or MercedesBenzOfficialPriceParser()
        self._shared_service = VolkswagenOfficialPriceImportService(session)

    def import_html(
        self,
        path: Path | str,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> MercedesBenzOfficialPriceImportResult:
        """Parse and import one local Mercedes-Benz Germany HTML fixture."""

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
    ) -> MercedesBenzOfficialPriceImportResult:
        """Import parsed official price records through the shared service."""

        return self._shared_service.import_records(records)
