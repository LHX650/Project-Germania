"""Skoda Germany official price import foundation."""

from __future__ import annotations

from germania.collectors.skoda.config import (
    SKODA_DE_BASE_URL,
    SKODA_DE_COUNTRY_CODE,
    SKODA_DE_SOURCE_ID,
)
from germania.collectors.skoda.import_service import (
    SkodaOfficialPriceImportResult,
    SkodaOfficialPriceImportService,
)
from germania.collectors.skoda.parser import (
    SkodaOfficialPriceParser,
    parse_skoda_official_prices,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord

__all__ = [
    "SKODA_DE_BASE_URL",
    "SKODA_DE_COUNTRY_CODE",
    "SKODA_DE_SOURCE_ID",
    "OfficialPriceRecord",
    "SkodaOfficialPriceImportResult",
    "SkodaOfficialPriceImportService",
    "SkodaOfficialPriceParser",
    "parse_skoda_official_prices",
]
