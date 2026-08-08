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
from germania.collectors.autoscout24.matching import (
    VehicleMatchSummary,
    combine_match_summaries,
)
from germania.collectors.autoscout24.parser import AutoScout24ListingParser
from germania.collectors.autoscout24.run_management import (
    CollectionBatchOutcome,
    CollectionBatchStatus,
    create_task_collection_batch,
    finalize_task_collection_batch,
    generate_collection_run_id,
    validate_collection_run_id,
)
from germania.collectors.exceptions import RequestBudgetExceeded
from germania.config.marketplace_collection import CollectionTask
from germania.db.models import CollectionBatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoScout24TaskCollectionResult:
    """Flattened collection and import statistics for one configured task."""

    task_id: str
    cohort: str
    brand_name: str
    model_name: str
    collection_batch_id: int | None
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    page_success_rate: float
    parsed: int
    matching: VehicleMatchSummary
    inserted: int
    updated: int
    skipped: int
    rejected: int
    price_history_inserted: int
    observations_inserted: int
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether at least one requested page completed successfully."""
        return self.error_message is None and self.succeeded_pages > 0


@dataclass(frozen=True)
class AutoScout24MultiModelCollectionResult:
    """Overall and per-model statistics for one multi-model collection run."""

    mode: BatchCollectionMode
    run_id: str
    requested_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    page_success_rate: float
    parsed: int
    matching: VehicleMatchSummary
    inserted: int
    updated: int
    skipped: int
    rejected: int
    price_history_inserted: int
    observations_inserted: int
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
        run_id: str | None = None,
    ) -> AutoScout24MultiModelCollectionResult:
        """Collect enabled tasks sequentially while reusing browser resources."""

        if mode not in {"dry_run", "import"}:
            raise ValueError("mode must be either 'dry_run' or 'import'")

        selected_tasks = tuple(task for task in tasks if task.enabled)
        resolved_run_id = (
            validate_collection_run_id(run_id)
            if run_id is not None
            else generate_collection_run_id()
        )
        task_results: list[AutoScout24TaskCollectionResult] = []
        output_root = Path(raw_html_dir)
        try:
            self.collector.bind_run(resolved_run_id)
            _validate_page_budget(self.collector, selected_tasks)
            self.collector.preflight()
            for index, task in enumerate(selected_tasks):
                task_results.append(
                    self._run_task(
                        task,
                        raw_html_dir=output_root,
                        mode=mode,
                        run_id=resolved_run_id,
                    )
                )
                if self.collector.source_circuit_open:
                    error_message = self.collector.source_circuit_error or (
                        "AutoScout24 source circuit opened"
                    )
                    task_results.extend(
                        _failed_task_result(
                            remaining_task,
                            f"Skipped after source access denial: {error_message}",
                        )
                        for remaining_task in selected_tasks[index + 1 :]
                    )
                    break
        finally:
            self.collector.close()

        return _combine_task_results(mode, resolved_run_id, task_results)

    def _run_task(
        self,
        task: CollectionTask,
        *,
        raw_html_dir: Path,
        mode: BatchCollectionMode,
        run_id: str,
    ) -> AutoScout24TaskCollectionResult:
        if task.source_id != AUTOSCOUT24_DE_SOURCE_ID:
            return _failed_task_result(
                task,
                f"Unsupported source_id for AutoScout24 pipeline: {task.source_id}",
            )

        task_raw_html_dir = raw_html_dir / task.task_id
        collection_batch = None
        try:
            if mode == "import":
                collection_batch = create_task_collection_batch(
                    self.session,
                    run_id=run_id,
                    task=task,
                    raw_html_dir=task_raw_html_dir,
                )
            result = AutoScout24BatchCollectionPipeline(
                self.collector,
                self.session,
                parser=self.parser,
            ).run(
                SearchConfig(
                    brand=task.brand_name,
                    model=(
                        task.search_keywords[0]
                        if task.search_keywords
                        else task.model_name
                    ),
                    search_url=task.search_url,
                    expected_model_name=task.model_name,
                    included_title_terms=(
                        task.search_keywords
                        if task.search_keywords
                        else (task.model_name,)
                    ),
                    excluded_title_terms=task.excluded_title_terms,
                ),
                raw_html_dir=task_raw_html_dir,
                max_pages=task.max_pages,
                mode=mode,
                close_collector=False,
                collection_batch_id=(
                    collection_batch.collection_batch_id
                    if collection_batch is not None
                    else None
                ),
            )
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "AutoScout24 multi-model task failed task_id=%s error=%s",
                task.task_id,
                error_message,
            )
            failed_result = _failed_task_result(
                task,
                error_message,
                collection_batch_id=(
                    collection_batch.collection_batch_id
                    if collection_batch is not None
                    else None
                ),
            )
            if collection_batch is not None:
                _finalize_collection_batch(
                    self.session,
                    collection_batch,
                    task,
                    failed_result,
                )
            return failed_result

        import_result = result.import_result
        error_message = None
        if result.succeeded_pages == 0:
            error_message = "No requested pages completed successfully"
        task_result = AutoScout24TaskCollectionResult(
            task_id=task.task_id,
            cohort=task.cohort,
            brand_name=task.brand_name,
            model_name=task.model_name,
            collection_batch_id=(
                collection_batch.collection_batch_id
                if collection_batch is not None
                else None
            ),
            requested_pages=result.requested_pages,
            succeeded_pages=result.succeeded_pages,
            failed_pages=result.failed_pages,
            page_success_rate=_page_success_rate(
                result.succeeded_pages,
                result.requested_pages,
            ),
            parsed=result.parsed,
            matching=result.matching,
            inserted=import_result.inserted,
            updated=import_result.updated,
            skipped=import_result.skipped,
            rejected=import_result.rejected,
            price_history_inserted=import_result.price_history_inserted,
            observations_inserted=import_result.observations_inserted,
            error_message=error_message,
        )
        if collection_batch is not None:
            _finalize_collection_batch(
                self.session,
                collection_batch,
                task,
                task_result,
            )
        return task_result


def _failed_task_result(
    task: CollectionTask,
    error_message: str,
    *,
    collection_batch_id: int | None = None,
) -> AutoScout24TaskCollectionResult:
    return AutoScout24TaskCollectionResult(
        task_id=task.task_id,
        cohort=task.cohort,
        brand_name=task.brand_name,
        model_name=task.model_name,
        collection_batch_id=collection_batch_id,
        requested_pages=task.max_pages,
        succeeded_pages=0,
        failed_pages=task.max_pages,
        page_success_rate=0.0,
        parsed=0,
        matching=VehicleMatchSummary(reason_counts={}),
        inserted=0,
        updated=0,
        skipped=0,
        rejected=0,
        price_history_inserted=0,
        observations_inserted=0,
        error_message=error_message,
    )


def _combine_task_results(
    mode: BatchCollectionMode,
    run_id: str,
    task_results: list[AutoScout24TaskCollectionResult],
) -> AutoScout24MultiModelCollectionResult:
    succeeded_tasks = sum(result.succeeded for result in task_results)
    requested_pages = sum(result.requested_pages for result in task_results)
    succeeded_pages = sum(result.succeeded_pages for result in task_results)
    return AutoScout24MultiModelCollectionResult(
        mode=mode,
        run_id=run_id,
        requested_tasks=len(task_results),
        succeeded_tasks=succeeded_tasks,
        failed_tasks=len(task_results) - succeeded_tasks,
        requested_pages=requested_pages,
        succeeded_pages=succeeded_pages,
        failed_pages=sum(result.failed_pages for result in task_results),
        page_success_rate=_page_success_rate(succeeded_pages, requested_pages),
        parsed=sum(result.parsed for result in task_results),
        matching=combine_match_summaries(result.matching for result in task_results),
        inserted=sum(result.inserted for result in task_results),
        updated=sum(result.updated for result in task_results),
        skipped=sum(result.skipped for result in task_results),
        rejected=sum(result.rejected for result in task_results),
        price_history_inserted=sum(
            result.price_history_inserted for result in task_results
        ),
        observations_inserted=sum(
            result.observations_inserted for result in task_results
        ),
        tasks=tuple(task_results),
    )


def _validate_page_budget(
    collector: AutoScout24Collector,
    tasks: tuple[CollectionTask, ...],
) -> None:
    requested_pages = sum(
        task.max_pages for task in tasks if task.source_id == AUTOSCOUT24_DE_SOURCE_ID
    )
    remaining_budget = collector.remaining_request_budget()
    remaining_source_budget = collector.remaining_source_request_budget
    if collector.preflight_required:
        remaining_budget -= 1
        remaining_source_budget -= 1
    remaining_budget = min(remaining_budget, remaining_source_budget)
    if requested_pages > remaining_budget:
        raise RequestBudgetExceeded(
            "Configured task pages exceed the remaining request budget: "
            f"requested_pages={requested_pages} remaining_budget={remaining_budget}"
        )


def _page_success_rate(succeeded_pages: int, requested_pages: int) -> float:
    if requested_pages == 0:
        return 0.0
    return succeeded_pages / requested_pages


def _finalize_collection_batch(
    session: Session,
    collection_batch: CollectionBatch,
    task: CollectionTask,
    result: AutoScout24TaskCollectionResult,
) -> None:
    status: CollectionBatchStatus = "completed"
    if result.succeeded_pages == 0:
        status = "failed"
    elif result.failed_pages:
        status = "partially_completed"
    finalize_task_collection_batch(
        session,
        collection_batch,
        task=task,
        outcome=CollectionBatchOutcome(
            status=status,
            requested_pages=result.requested_pages,
            succeeded_pages=result.succeeded_pages,
            failed_pages=result.failed_pages,
            parsed=result.parsed,
            matched=result.matching.matched,
            rejected=result.matching.rejected,
            low_confidence=result.matching.low_confidence,
            import_rejected=result.rejected,
            observations_inserted=result.observations_inserted,
            error_message=result.error_message,
        ),
    )
