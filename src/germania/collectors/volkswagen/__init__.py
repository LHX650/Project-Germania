"""Volkswagen Germany official price import foundation."""

from __future__ import annotations

from germania.collectors.volkswagen.config import (
    VOLKSWAGEN_DE_BASE_URL,
    VOLKSWAGEN_DE_COUNTRY_CODE,
    VOLKSWAGEN_DE_SOURCE_ID,
)
from germania.collectors.volkswagen.import_service import (
    VolkswagenOfficialPriceImportResult,
    VolkswagenOfficialPriceImportService,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord
from germania.collectors.volkswagen.parser import (
    VolkswagenOfficialPriceParser,
    parse_official_prices,
)

__all__ = [
    "VOLKSWAGEN_DE_BASE_URL",
    "VOLKSWAGEN_DE_COUNTRY_CODE",
    "VOLKSWAGEN_DE_SOURCE_ID",
    "OfficialPriceRecord",
    "VolkswagenOfficialPriceImportResult",
    "VolkswagenOfficialPriceImportService",
    "VolkswagenOfficialPriceParser",
    "parse_official_prices",
]
