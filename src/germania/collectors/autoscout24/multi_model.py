"""Configuration-driven multi-model AutoScout24 collection workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from germania.collectors.autoscout24.batch import (
    AutoScout24BatchCollectionPipeline,
    BatchCollectionMode,
)
from germania.collectors.autoscout24.collector import AutoScout24Collector
from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_SOURCE_ID,
    SearchConfig,
)
from germania.collectors.autoscout24.parser import AutoScout24ListingParser
from germania.config.marketplace_collection import CollectionTask

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoScout24TaskCollectionResult:
    """Flattened collection and import statistics for one configured task."""

    task_id: str
    brand_name: str
    model_name: str
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    parsed: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    price_history_inserted: int
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether at least one requested page completed successfully."""
        return self.error_message is None and self.succeeded_pages > 0


@dataclass(frozen=True)
class AutoScout24MultiModelCollectionResult:
    """Overall and per-model statistics for one multi-model collection run."""

    mode: BatchCollectionMode
    requested_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    parsed: int
    inserted: int
    updated: int
    skipped: int
    rejected: int
    price_history_inserted: int
    tasks: tuple[AutoScout24TaskCollectionResult, ...]


class AutoScout24MultiModelCollectionPipeline:
    """Run multiple bounded batches with one browser, context, and page."""

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
        tasks: tuple[CollectionTask, ...] | list[CollectionTask],
        *,
        raw_html_dir: Path | str,
        mode: BatchCollectionMode = "import",
    ) -> AutoScout24MultiModelCollectionResult:
        """Collect enabled tasks sequentially while reusing browser resources."""

        if mode not in {"dry_run", "import"}:
            raise ValueError("mode must be either 'dry_run' or 'import'")

        selected_tasks = tuple(task for task in tasks if task.enabled)
        task_results: list[AutoScout24TaskCollectionResult] = []
        output_root = Path(raw_html_dir)
        try:
            for task in selected_tasks:
                task_results.append(
                    self._run_task(task, raw_html_dir=output_root, mode=mode)
                )
        finally:
            self.collector.close()

        return _combine_task_results(mode, task_results)

    def _run_task(
        self,
        task: CollectionTask,
        *,
        raw_html_dir: Path,
        mode: BatchCollectionMode,
    ) -> AutoScout24TaskCollectionResult:
        if task.source_id != AUTOSCOUT24_DE_SOURCE_ID:
            return _failed_task_result(
                task,
                f"Unsupported source_id for AutoScout24 pipeline: {task.source_id}",
            )

        try:
            result = AutoScout24BatchCollectionPipeline(
                self.collector,
                self.session,
                parser=self.parser,
            ).run(
                SearchConfig(
                    brand=task.brand_name,
                    model=task.model_name,
                    search_url=task.search_url,
                    excluded_title_terms=task.excluded_title_terms,
                ),
                raw_html_dir=raw_html_dir / task.task_id,
                max_pages=task.max_pages,
                mode=mode,
                close_collector=False,
            )
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "AutoScout24 multi-model task failed task_id=%s error=%s",
                task.task_id,
                error_message,
            )
            return _failed_task_result(task, error_message)

        import_result = result.import_result
        error_message = None
        if result.succeeded_pages == 0:
            error_message = "No requested pages completed successfully"
        return AutoScout24TaskCollectionResult(
            task_id=task.task_id,
            brand_name=task.brand_name,
            model_name=task.model_name,
            requested_pages=result.requested_pages,
            succeeded_pages=result.succeeded_pages,
            failed_pages=result.failed_pages,
            parsed=result.parsed,
            inserted=import_result.inserted,
            updated=import_result.updated,
            skipped=import_result.skipped,
            rejected=import_result.rejected,
            price_history_inserted=import_result.price_history_inserted,
            error_message=error_message,
        )


def _failed_task_result(
    task: CollectionTask,
    error_message: str,
) -> AutoScout24TaskCollectionResult:
    return AutoScout24TaskCollectionResult(
        task_id=task.task_id,
        brand_name=task.brand_name,
        model_name=task.model_name,
        requested_pages=task.max_pages,
        succeeded_pages=0,
        failed_pages=task.max_pages,
        parsed=0,
        inserted=0,
        updated=0,
        skipped=0,
        rejected=0,
        price_history_inserted=0,
        error_message=error_message,
    )


def _combine_task_results(
    mode: BatchCollectionMode,
    task_results: list[AutoScout24TaskCollectionResult],
) -> AutoScout24MultiModelCollectionResult:
    succeeded_tasks = sum(result.succeeded for result in task_results)
    return AutoScout24MultiModelCollectionResult(
        mode=mode,
        requested_tasks=len(task_results),
        succeeded_tasks=succeeded_tasks,
        failed_tasks=len(task_results) - succeeded_tasks,
        requested_pages=sum(result.requested_pages for result in task_results),
        succeeded_pages=sum(result.succeeded_pages for result in task_results),
        failed_pages=sum(result.failed_pages for result in task_results),
        parsed=sum(result.parsed for result in task_results),
        inserted=sum(result.inserted for result in task_results),
        updated=sum(result.updated for result in task_results),
        skipped=sum(result.skipped for result in task_results),
        rejected=sum(result.rejected for result in task_results),
        price_history_inserted=sum(
            result.price_history_inserted for result in task_results
        ),
        tasks=tuple(task_results),
    )
