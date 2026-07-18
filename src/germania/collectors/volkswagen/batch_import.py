"""Batch import local Volkswagen Germany official price files."""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.volkswagen.config import VOLKSWAGEN_DE_SOURCE_ID
from germania.collectors.volkswagen.import_service import (
    VolkswagenOfficialPriceImportResult,
    VolkswagenOfficialPriceImportService,
)
from germania.collectors.volkswagen.models import OfficialPriceRecord
from germania.collectors.volkswagen.parser import VolkswagenOfficialPriceParser
from germania.db import session_scope

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_VOLKSWAGEN_PRICE_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "volkswagen"
SUPPORTED_OFFICIAL_PRICE_SUFFIXES = frozenset({".csv", ".html", ".htm"})
REQUIRED_CSV_FIELDS = frozenset(
    {
        "canonical_brand_name",
        "canonical_model_name",
        "original_currency",
        "original_price",
        "price_eur",
        "price_type",
        "raw_variant_name",
        "valid_date",
    }
)
_DATED_FILE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[-_ .](?P<month>0?[1-9]|1[0-2])"),
    re.compile(r"(?P<year>20\d{2})(?P<month>0[1-9]|1[0-2])"),
)


class VolkswagenOfficialPriceBatchImportError(ValueError):
    """Raised when a Volkswagen official price batch cannot be prepared."""


@dataclass(frozen=True)
class VolkswagenOfficialPriceBatchFileResult:
    """Summary for one official price file processed in a batch."""

    file_path: Path
    total: int
    matched: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    succeeded: bool
    error: str | None = None

    @classmethod
    def from_import_result(
        cls,
        file_path: Path,
        result: VolkswagenOfficialPriceImportResult,
    ) -> VolkswagenOfficialPriceBatchFileResult:
        """Create a successful file result from one import result."""

        return cls(
            file_path=file_path,
            total=result.total,
            matched=result.inserted + result.updated + result.skipped,
            inserted=result.inserted,
            updated=result.updated,
            skipped=result.skipped,
            rejected=result.rejected,
            succeeded=True,
        )

    @classmethod
    def failed(
        cls,
        file_path: Path,
        error: Exception,
    ) -> VolkswagenOfficialPriceBatchFileResult:
        """Create a failed file result with zero imported records."""

        return cls(
            file_path=file_path,
            total=0,
            matched=0,
            inserted=0,
            updated=0,
            skipped=0,
            rejected=0,
            succeeded=False,
            error=f"{type(error).__name__}: {error}",
        )


@dataclass(frozen=True)
class VolkswagenOfficialPriceBatchImportResult:
    """Aggregate summary for a Volkswagen official price batch import."""

    file_results: tuple[VolkswagenOfficialPriceBatchFileResult, ...]
    total: int
    matched: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    succeeded: int
    failed: int

    @classmethod
    def from_file_results(
        cls,
        file_results: list[VolkswagenOfficialPriceBatchFileResult],
    ) -> VolkswagenOfficialPriceBatchImportResult:
        """Create aggregate counts from per-file results."""

        return cls(
            file_results=tuple(file_results),
            total=sum(result.total for result in file_results),
            matched=sum(result.matched for result in file_results),
            inserted=sum(result.inserted for result in file_results),
            updated=sum(result.updated for result in file_results),
            skipped=sum(result.skipped for result in file_results),
            rejected=sum(result.rejected for result in file_results),
            succeeded=sum(1 for result in file_results if result.succeeded),
            failed=sum(1 for result in file_results if not result.succeeded),
        )

    @property
    def file_count(self) -> int:
        """Return the number of files considered by the batch run."""

        return len(self.file_results)


class VolkswagenOfficialPriceBatchImportService:
    """Import multiple local Volkswagen official price files."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        parser: VolkswagenOfficialPriceParser | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.parser = parser or VolkswagenOfficialPriceParser()

    def import_directory(
        self,
        directory: Path | str = DEFAULT_VOLKSWAGEN_PRICE_RAW_DIR,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> VolkswagenOfficialPriceBatchImportResult:
        """Import all supported official price files in a directory by date."""

        return self.import_paths(
            _discover_supported_files(directory),
            source_url=source_url,
            collected_at=collected_at,
        )

    def import_paths(
        self,
        paths: Iterable[Path | str],
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
    ) -> VolkswagenOfficialPriceBatchImportResult:
        """Import explicit official price file paths by file date."""

        file_results: list[VolkswagenOfficialPriceBatchFileResult] = []
        for file_path in _sort_paths_by_file_date(paths):
            try:
                with session_scope(self.session_factory) as session:
                    service = VolkswagenOfficialPriceImportService(
                        session,
                        parser=self.parser,
                    )
                    import_result = _import_file(
                        service,
                        file_path,
                        source_url=source_url,
                        collected_at=collected_at or _collected_at_from_file(file_path),
                    )
                file_results.append(
                    VolkswagenOfficialPriceBatchFileResult.from_import_result(
                        file_path,
                        import_result,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Volkswagen official price batch import failed for %s",
                    file_path,
                    exc_info=True,
                )
                file_results.append(
                    VolkswagenOfficialPriceBatchFileResult.failed(file_path, exc)
                )

        return VolkswagenOfficialPriceBatchImportResult.from_file_results(file_results)


def _import_file(
    service: VolkswagenOfficialPriceImportService,
    file_path: Path,
    *,
    source_url: str | None,
    collected_at: datetime,
) -> VolkswagenOfficialPriceImportResult:
    suffix = file_path.suffix.casefold()
    if suffix in {".html", ".htm"}:
        return service.import_html(
            file_path,
            source_url=source_url,
            collected_at=collected_at,
        )
    if suffix == ".csv":
        records = _parse_csv_file(
            file_path,
            source_url=source_url,
            collected_at=collected_at,
        )
        return service.import_records(records)
    raise VolkswagenOfficialPriceBatchImportError(
        f"Unsupported official price file type: {file_path}"
    )


def _parse_csv_file(
    file_path: Path,
    *,
    source_url: str | None,
    collected_at: datetime,
) -> list[OfficialPriceRecord]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        _validate_csv_fields(reader.fieldnames, file_path)
        return [
            _record_from_csv_row(
                row,
                row_number=row_number,
                source_url=source_url,
                collected_at=collected_at,
            )
            for row_number, row in enumerate(reader, start=2)
        ]


def _record_from_csv_row(
    row: dict[str, str],
    *,
    row_number: int,
    source_url: str | None,
    collected_at: datetime,
) -> OfficialPriceRecord:
    row_source_url = _optional_text(row, "source_url") or source_url
    row_collected_at = _optional_datetime(row, "collected_at") or collected_at
    original_currency = _required_text(row, "original_currency", row_number)
    price_eur = _required_decimal(row, "price_eur", row_number)
    original_price = _required_decimal(row, "original_price", row_number)

    return OfficialPriceRecord(
        source_url=row_source_url,
        raw_brand_name=_optional_text(row, "raw_brand_name"),
        raw_model_name=_optional_text(row, "raw_model_name"),
        raw_variant_name=_required_text(row, "raw_variant_name", row_number),
        canonical_brand_name=_required_text(
            row,
            "canonical_brand_name",
            row_number,
        ),
        canonical_model_name=_required_text(
            row,
            "canonical_model_name",
            row_number,
        ),
        price_type=_required_text(row, "price_type", row_number),
        original_price=original_price,
        original_currency=original_currency,
        price_eur=price_eur,
        raw_price_text=_optional_text(row, "raw_price_text"),
        observed_at=_optional_datetime(row, "observed_at"),
        valid_date=_required_date(row, "valid_date", row_number),
        collected_at=row_collected_at,
        source_id=_optional_text(row, "source_id") or VOLKSWAGEN_DE_SOURCE_ID,
        price_includes_vat=_optional_bool(row, "price_includes_vat"),
    )


def _validate_csv_fields(fieldnames: list[str] | None, file_path: Path) -> None:
    if fieldnames is None:
        raise VolkswagenOfficialPriceBatchImportError(
            f"Official price CSV is missing a header row: {file_path}"
        )
    missing_fields = REQUIRED_CSV_FIELDS.difference(fieldnames)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise VolkswagenOfficialPriceBatchImportError(
            f"Official price CSV {file_path} is missing required fields: {missing}"
        )


def _discover_supported_files(directory: Path | str) -> list[Path]:
    raw_dir = Path(directory)
    if not raw_dir.exists():
        raise VolkswagenOfficialPriceBatchImportError(
            f"Official price directory not found: {raw_dir}"
        )
    if not raw_dir.is_dir():
        raise VolkswagenOfficialPriceBatchImportError(
            f"Official price path is not a directory: {raw_dir}"
        )
    return [
        path
        for path in raw_dir.iterdir()
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_OFFICIAL_PRICE_SUFFIXES
    ]


def _sort_paths_by_file_date(paths: Iterable[Path | str]) -> list[Path]:
    return sorted((Path(path) for path in paths), key=_file_date_sort_key)


def _file_date_sort_key(path: Path) -> tuple[int, int, str]:
    for pattern in _DATED_FILE_PATTERNS:
        match = pattern.search(path.stem)
        if match is not None:
            return int(match.group("year")), int(match.group("month")), path.name
    return 9999, 99, path.name


def _collected_at_from_file(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _optional_text(row: dict[str, str], field_name: str) -> str | None:
    value = row.get(field_name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_text(row: dict[str, str], field_name: str, row_number: int) -> str:
    value = _optional_text(row, field_name)
    if value is None:
        raise VolkswagenOfficialPriceBatchImportError(
            f"CSV row {row_number} requires non-empty {field_name}"
        )
    return value


def _required_decimal(
    row: dict[str, str],
    field_name: str,
    row_number: int,
) -> Decimal:
    value = _required_text(row, field_name, row_number)
    try:
        return Decimal(_normalize_decimal_text(value))
    except InvalidOperation as exc:
        raise VolkswagenOfficialPriceBatchImportError(
            f"CSV row {row_number} has invalid decimal {field_name}: {value}"
        ) from exc


def _required_date(row: dict[str, str], field_name: str, row_number: int) -> date:
    value = _required_text(row, field_name, row_number)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise VolkswagenOfficialPriceBatchImportError(
            f"CSV row {row_number} has invalid date {field_name}: {value}"
        ) from exc


def _optional_datetime(row: dict[str, str], field_name: str) -> datetime | None:
    value = _optional_text(row, field_name)
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise VolkswagenOfficialPriceBatchImportError(
            f"CSV has invalid datetime {field_name}: {value}"
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _optional_bool(row: dict[str, str], field_name: str) -> bool | None:
    value = _optional_text(row, field_name)
    if value is None:
        return None
    normalized = value.casefold()
    if normalized in {"true", "yes", "1", "ja"}:
        return True
    if normalized in {"false", "no", "0", "nein"}:
        return False
    raise VolkswagenOfficialPriceBatchImportError(
        f"CSV has invalid boolean {field_name}: {value}"
    )


def _normalize_decimal_text(value: str) -> str:
    normalized = value.replace(" ", "").strip(".,")
    if "," in normalized and "." in normalized:
        return normalized.replace(".", "").replace(",", ".").strip(".")
    if "," in normalized:
        before, _, after = normalized.partition(",")
        if len(after) == 2:
            return f"{before}.{after}"
        return normalized.replace(",", "")
    if normalized.count(".") == 1:
        before, _, after = normalized.partition(".")
        if len(after) == 2:
            return f"{before}.{after}"
    return normalized.replace(".", "")
