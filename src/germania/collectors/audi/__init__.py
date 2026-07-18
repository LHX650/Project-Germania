"""Audi Germany official price import foundation."""

from __future__ import annotations

from germania.collectors.audi.config import (
    AUDI_DE_BASE_URL,
    AUDI_DE_COUNTRY_CODE,
    AUDI_DE_SOURCE_ID,
)
from germania.collectors.audi.import_service import (
    AudiOfficialPriceImportResult,
    AudiOfficialPriceImportService,
)
from germania.collectors.audi.parser import (
    AudiOfficialPriceParser,
    parse_audi_official_prices,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord

__all__ = [
    "AUDI_DE_BASE_URL",
    "AUDI_DE_COUNTRY_CODE",
    "AUDI_DE_SOURCE_ID",
    "AudiOfficialPriceImportResult",
    "AudiOfficialPriceImportService",
    "AudiOfficialPriceParser",
    "OfficialPriceRecord",
    "parse_audi_official_prices",
]
