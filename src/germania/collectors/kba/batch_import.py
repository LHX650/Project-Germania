"""Batch import local KBA registration workbooks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from germania.collectors.kba.import_service import KBAImportResult, KBAImportService
from germania.collectors.kba.name_mapping import KBANameMapping
from germania.collectors.kba.parser import KBAXlsxParser
from germania.db import session_scope

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_KBA_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "kba"
_DATED_FILE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[-_ .](?P<month>0?[1-9]|1[0-2])"),
    re.compile(r"(?P<year>20\d{2})(?P<month>0[1-9]|1[0-2])"),
)


class KBABatchImportError(ValueError):
    """Raised when a KBA batch import cannot be prepared."""


@dataclass(frozen=True)
class KBABatchImportFileResult:
    """Summary for one file processed during a KBA batch import."""

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
        result: KBAImportResult,
    ) -> KBABatchImportFileResult:
        """Create a successful file result from one KBA import result."""

        return cls(
            file_path=file_path,
            total=result.total,
            matched=result.matched,
            inserted=result.inserted,
            updated=result.updated,
            skipped=result.skipped,
            rejected=result.rejected,
            succeeded=True,
        )

    @classmethod
    def failed(cls, file_path: Path, error: Exception) -> KBABatchImportFileResult:
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
class KBABatchImportResult:
    """Summary for a complete KBA batch import run."""

    file_results: tuple[KBABatchImportFileResult, ...]
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
        file_results: list[KBABatchImportFileResult],
    ) -> KBABatchImportResult:
        """Create an aggregate summary from per-file import results."""

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


class KBABatchImportService:
    """Import multiple local KBA workbooks through the single-file service."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        parser: KBAXlsxParser | None = None,
        name_mapping: KBANameMapping | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.parser = parser or KBAXlsxParser()
        self.name_mapping = name_mapping or KBANameMapping.load()

    def import_directory(
        self,
        directory: Path | str = DEFAULT_KBA_RAW_DIR,
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
        registration_scope: str = "Germany",
        country_code: str = "DE",
    ) -> KBABatchImportResult:
        """Import all local KBA XLSX files in a directory by file date."""

        return self.import_paths(
            _discover_xlsx_files(directory),
            source_url=source_url,
            collected_at=collected_at,
            registration_scope=registration_scope,
            country_code=country_code,
        )

    def import_paths(
        self,
        paths: list[Path | str],
        *,
        source_url: str | None = None,
        collected_at: datetime | None = None,
        registration_scope: str = "Germany",
        country_code: str = "DE",
    ) -> KBABatchImportResult:
        """Import explicit local KBA XLSX paths by file date."""

        file_results: list[KBABatchImportFileResult] = []
        for file_path in _sort_paths_by_file_date(paths):
            try:
                with session_scope(self.session_factory) as session:
                    service = KBAImportService(
                        session,
                        parser=self.parser,
                        name_mapping=self.name_mapping,
                    )
                    import_result = service.import_xlsx(
                        file_path,
                        source_url=source_url,
                        collected_at=collected_at or _collected_at_from_file(file_path),
                        registration_scope=registration_scope,
                        country_code=country_code,
                    )
                file_results.append(
                    KBABatchImportFileResult.from_import_result(
                        file_path,
                        import_result,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "KBA batch import failed for %s",
                    file_path,
                    exc_info=True,
                )
                file_results.append(KBABatchImportFileResult.failed(file_path, exc))

        return KBABatchImportResult.from_file_results(file_results)


def _discover_xlsx_files(directory: Path | str) -> list[Path]:
    raw_dir = Path(directory)
    if not raw_dir.exists():
        raise KBABatchImportError(f"KBA raw data directory not found: {raw_dir}")
    if not raw_dir.is_dir():
        raise KBABatchImportError(f"KBA raw data path is not a directory: {raw_dir}")
    return list(raw_dir.glob("*.xlsx"))


def _sort_paths_by_file_date(paths: list[Path | str]) -> list[Path]:
    return sorted((Path(path) for path in paths), key=_file_date_sort_key)


def _file_date_sort_key(path: Path) -> tuple[int, int, str]:
    for pattern in _DATED_FILE_PATTERNS:
        match = pattern.search(path.stem)
        if match is not None:
            return int(match.group("year")), int(match.group("month")), path.name
    return 9999, 99, path.name


def _collected_at_from_file(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
