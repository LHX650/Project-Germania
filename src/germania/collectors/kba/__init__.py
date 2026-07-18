"""KBA official registration import foundation."""

from __future__ import annotations

from germania.collectors.kba.field_mapping import (
    DEFAULT_FUEL_TYPE,
    FIELD_ALIASES,
    FUEL_COLUMN_ALIASES,
    KBA_SOURCE_ID,
    HeaderMapping,
    resolve_fuel_type_value,
)
from germania.collectors.kba.import_service import KBAImportResult, KBAImportService
from germania.collectors.kba.models import RegistrationRecord
from germania.collectors.kba.name_mapping import KBANameMapping, KBANameMappingError
from germania.collectors.kba.parser import (
    KBAXlsxParser,
    KBAXlsxParserError,
    parse_kba_fz10_xlsx,
)

__all__ = [
    "DEFAULT_FUEL_TYPE",
    "FIELD_ALIASES",
    "FUEL_COLUMN_ALIASES",
    "KBA_SOURCE_ID",
    "HeaderMapping",
    "KBAImportResult",
    "KBAImportService",
    "KBANameMapping",
    "KBANameMappingError",
    "KBAXlsxParser",
    "KBAXlsxParserError",
    "RegistrationRecord",
    "parse_kba_fz10_xlsx",
    "resolve_fuel_type_value",
]
