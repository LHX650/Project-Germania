"""BMW Germany official price import foundation."""

from __future__ import annotations

from germania.collectors.bmw.config import (
    BMW_DE_BASE_URL,
    BMW_DE_COUNTRY_CODE,
    BMW_DE_SOURCE_ID,
)
from germania.collectors.bmw.import_service import (
    BMWOfficialPriceImportResult,
    BMWOfficialPriceImportService,
)
from germania.collectors.bmw.parser import (
    BMWOfficialPriceParser,
    parse_bmw_official_prices,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord

__all__ = [
    "BMW_DE_BASE_URL",
    "BMW_DE_COUNTRY_CODE",
    "BMW_DE_SOURCE_ID",
    "BMWOfficialPriceImportResult",
    "BMWOfficialPriceImportService",
    "BMWOfficialPriceParser",
    "OfficialPriceRecord",
    "parse_bmw_official_prices",
]
