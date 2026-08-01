"""Batch AutoScout24 collection, parsing, and import workflow."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from germania.collectors.autoscout24.collector import (
    AutoScout24Collector,
    ListingPageLoadFailure,
    LoadedListingPage,
)
from germania.collectors.autoscout24.config import SearchConfig
from germania.collectors.autoscout24.import_service import (
    AutoScout24ImportResult,
    AutoScout24ListingImportService,
    combine_import_results,
)
from germania.collectors.autoscout24.matching import (
    VehicleMatchSummary,
    combine_match_summaries,
    evaluate_vehicle_matches,
)
from germania.collectors.autoscout24.parser import AutoScout24ListingParser
from germania.collectors.autoscout24.single_page import _save_raw_html
from germania.collectors.marketplace import MarketplaceListingRecord

logger = logging.getLogger(__name__)

BatchCollectionMode = Literal["dry_run", "import"]


@dataclass(frozen=True)
class AutoScout24BatchPageResult:
    """Traceable result for one page in a batch collection workflow."""

    page: int
    url: str
    raw_html_path: Path | None
    content_sha256: str | None
    parsed: int
    matching: VehicleMatchSummary
    import_result: AutoScout24ImportResult
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether this page loaded and processed successfully."""
        return self.error_message is None


@dataclass(frozen=True)
class AutoScout24BatchCollectionResult:
    """Summary for one multi-page AutoScout24 batch collection workflow."""

    mode: BatchCollectionMode
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    parsed: int
    matching: VehicleMatchSummary
    import_result: AutoScout24ImportResult
    pages: tuple[AutoScout24BatchPageResult, ...]


class AutoScout24BatchCollectionPipeline:
    """Run a bounded multi-page AutoScout24 collection workflow."""

    def __init__(
        self,
        collector: AutoScout24Collector,
        session: Session,
        *,
        parser: AutoScout24ListingParser | None = None,
    ) -> None:
        self.collector = collector
        self.session = session
        self.parser = parser or AutoScout24ListingParser()

    def run(
        self,
        search_config: SearchConfig,
        *,
        raw_html_dir: Path | str,
        max_pages: int = 3,
        mode: BatchCollectionMode = "import",
        close_collector: bool = True,
        collection_batch_id: int | None = None,
    ) -> AutoScout24BatchCollectionResult:
        """Collect, preserve, parse, and import a bounded page range.

        ``close_collector=False`` lets a higher-level workflow reuse the same
        browser resources across multiple bounded batches.
        """

        if mode not in {"dry_run", "import"}:
            raise ValueError("mode must be either 'dry_run' or 'import'")
        if max_pages <= 0:
            raise ValueError("max_pages must be a positive integer")

        page_results: list[AutoScout24BatchPageResult] = []
        service = AutoScout24ListingImportService(self.session, parser=self.parser)

        try:
            loaded_pages = self.collector.load_listing_pages(
                search_config,
                max_pages=max_pages,
            )
            for loaded_page in loaded_pages:
                page_results.append(
                    self._process_page(
                        loaded_page,
                        raw_html_dir=Path(raw_html_dir),
                        service=service,
                        mode=mode,
                        collection_batch_id=collection_batch_id,
                    )
                )
        finally:
            if close_collector:
                self.collector.close()

        successful_results = [result for result in page_results if result.succeeded]
        return AutoScout24BatchCollectionResult(
            mode=mode,
            requested_pages=max_pages,
            succeeded_pages=len(successful_results),
            failed_pages=len(page_results) - len(successful_results),
            parsed=sum(result.parsed for result in successful_results),
            matching=combine_match_summaries(
                result.matching for result in successful_results
            ),
            import_result=combine_import_results(
                result.import_result for result in successful_results
            ),
            pages=tuple(page_results),
        )

    def _process_page(
        self,
        loaded_page: LoadedListingPage | ListingPageLoadFailure,
        *,
        raw_html_dir: Path,
        service: AutoScout24ListingImportService,
        mode: BatchCollectionMode,
        collection_batch_id: int | None,
    ) -> AutoScout24BatchPageResult:
        page_number = loaded_page.search_config.page
        if isinstance(loaded_page, ListingPageLoadFailure):
            return _failed_page_result(
                page=page_number,
                url=loaded_page.url,
                error_message=loaded_page.error_message,
            )

        try:
            saved_path = _save_raw_html(
                raw_html_dir / f"page_{page_number:03d}.html",
                loaded_page.html,
            )
            records = self.parser.parse_marketplace_listing_page(
                loaded_page.html,
                collected_at=loaded_page.metadata.collected_at,
            )
            match_evaluation = evaluate_vehicle_matches(
                records,
                expected_model_name=(
                    loaded_page.search_config.expected_model_name
                    or loaded_page.search_config.model
                ),
                include_keywords=loaded_page.search_config.included_title_terms,
                exclude_keywords=loaded_page.search_config.excluded_title_terms,
            )
            records = list(match_evaluation.records)
            if mode == "dry_run":
                import_result = service.dry_run_records(records)
            else:
                import_result = _import_records_in_savepoint(
                    service,
                    records,
                    collection_batch_id=collection_batch_id,
                )
            return AutoScout24BatchPageResult(
                page=page_number,
                url=loaded_page.url,
                raw_html_path=saved_path,
                content_sha256=loaded_page.metadata.content_sha256,
                parsed=len(records),
                matching=match_evaluation.summary,
                import_result=import_result,
            )
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "AutoScout24 batch page processing failed page=%s url=%s error=%s",
                page_number,
                loaded_page.url,
                error_message,
            )
            return _failed_page_result(
                page=page_number,
                url=loaded_page.url,
                error_message=error_message,
            )


def _import_records_in_savepoint(
    service: AutoScout24ListingImportService,
    records: Iterable[MarketplaceListingRecord],
    *,
    collection_batch_id: int | None,
) -> AutoScout24ImportResult:
    transaction = service.session.begin_nested()
    try:
        result = service.import_records(
            records,
            collection_batch_id=collection_batch_id,
        )
        transaction.commit()
        return result
    except Exception:
        if transaction.is_active:
            transaction.rollback()
        service.session.expire_all()
        raise


def _failed_page_result(
    *,
    page: int,
    url: str,
    error_message: str,
) -> AutoScout24BatchPageResult:
    return AutoScout24BatchPageResult(
        page=page,
        url=url,
        raw_html_path=None,
        content_sha256=None,
        parsed=0,
        matching=VehicleMatchSummary(reason_counts={}),
        import_result=AutoScout24ImportResult(
            total=0,
            inserted=0,
            updated=0,
            skipped=0,
            rejected=0,
            price_history_inserted=0,
            observations_inserted=0,
        ),
        error_message=error_message,
    )


def _apply_title_exclusions(
    records: list[MarketplaceListingRecord],
    excluded_title_terms: tuple[str, ...],
) -> list[MarketplaceListingRecord]:
    if not excluded_title_terms:
        return records

    normalized_terms = tuple(term.casefold() for term in excluded_title_terms)
    excluded = 0
    output: list[MarketplaceListingRecord] = []
    for record in records:
        normalized_title = (record.title or "").casefold()
        if any(term in normalized_title for term in normalized_terms):
            output.append(replace(record, model_name=None))
            excluded += 1
        else:
            output.append(record)

    if excluded:
        logger.warning(
            "AutoScout24 task title exclusions matched records=%s total=%s terms=%s",
            excluded,
            len(records),
            ",".join(excluded_title_terms),
        )
    return output
