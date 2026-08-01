"""Run governed daily collection followed by read-only market analytics."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from germania.analytics import (
    build_daily_market_intelligence,
    write_daily_market_intelligence,
)
from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24MultiModelCollectionPipeline,
    AutoScout24MultiModelCollectionResult,
)
from germania.collectors.autoscout24.run_management import (
    validate_collection_run_id,
)
from germania.config import CollectionTask, load_collection_tasks
from germania.db import create_database_engine, create_session_factory, session_scope

logger = logging.getLogger(__name__)

DEFAULT_COHORTS = ("core_a", "core_b")
DEFAULT_RAW_OUTPUT_ROOT = Path("data/raw/autoscout24/daily")
DEFAULT_ANALYTICS_OUTPUT = Path("reports/daily_market_intelligence.json")
_FILESYSTEM_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class FailedTaskSummary:
    """One failed collection task reported by a cohort pipeline."""

    task_id: str
    error_message: str


@dataclass(frozen=True)
class DailyCohortSummary:
    """Auditable result for one daily collection cohort."""

    cohort: str
    status: str
    raw_html_dir: str
    requested_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    listings_inserted: int
    observations_inserted: int
    price_history_inserted: int
    task_failures: tuple[FailedTaskSummary, ...]
    error_message: str | None = None


@dataclass(frozen=True)
class DailyMarketMonitorSummary:
    """Aggregate daily collection result suitable for scheduler logs."""

    run_id: str
    run_date: str
    started_at: str
    completed_at: str
    status: str
    successful_cohorts: int
    failed_cohorts: int
    listings_inserted: int
    observations_inserted: int
    price_history_inserted: int
    cohorts: tuple[DailyCohortSummary, ...]
    collection_status: str
    analytics_status: str
    analytics_report_path: str | None = None
    analytics_error_message: str | None = None


CohortRunner = Callable[
    [tuple[CollectionTask, ...], Path, str],
    AutoScout24MultiModelCollectionResult,
]
AnalyticsRunner = Callable[[], Path]


def run_daily_market_monitor(
    tasks: tuple[CollectionTask, ...],
    *,
    raw_output_root: Path,
    run_date: date,
    run_id: str,
    cohort_runner: CohortRunner,
    cohorts: tuple[str, ...] = DEFAULT_COHORTS,
    now_provider: Callable[[], datetime] | None = None,
) -> DailyMarketMonitorSummary:
    """Run configured cohorts independently and aggregate their statistics."""

    if not cohorts or len(set(cohorts)) != len(cohorts):
        raise ValueError("cohorts must be a non-empty sequence of unique names")
    resolved_run_id = validate_daily_run_id(run_id)
    active_now_provider = now_provider or _utc_now
    started_at = _as_utc(active_now_provider())
    run_root = reserve_run_output_directory(
        raw_output_root,
        run_date=run_date,
        run_id=resolved_run_id,
    )

    cohort_summaries: list[DailyCohortSummary] = []
    for cohort in cohorts:
        cohort_tasks = tuple(
            task for task in tasks if task.enabled and task.cohort == cohort
        )
        cohort_output_dir = run_root / cohort
        cohort_output_dir.mkdir()
        cohort_summaries.append(
            _run_cohort(
                cohort,
                cohort_tasks,
                cohort_output_dir=cohort_output_dir,
                run_id=resolved_run_id,
                cohort_runner=cohort_runner,
            )
        )

    completed_at = _as_utc(active_now_provider())
    successful_cohorts = sum(
        summary.status == "completed" for summary in cohort_summaries
    )
    failed_cohorts = len(cohort_summaries) - successful_cohorts
    collection_status = _overall_status(cohort_summaries)
    return DailyMarketMonitorSummary(
        run_id=resolved_run_id,
        run_date=run_date.isoformat(),
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        status=collection_status,
        successful_cohorts=successful_cohorts,
        failed_cohorts=failed_cohorts,
        listings_inserted=sum(
            summary.listings_inserted for summary in cohort_summaries
        ),
        observations_inserted=sum(
            summary.observations_inserted for summary in cohort_summaries
        ),
        price_history_inserted=sum(
            summary.price_history_inserted for summary in cohort_summaries
        ),
        cohorts=tuple(cohort_summaries),
        collection_status=collection_status,
        analytics_status="not_started",
    )


def run_analytics_after_collection(
    summary: DailyMarketMonitorSummary,
    *,
    analytics_runner: AnalyticsRunner,
) -> DailyMarketMonitorSummary:
    """Run analytics only after complete collection without changing its result."""

    if summary.collection_status != "completed":
        logger.warning(
            "Daily pipeline skipped analytics run_id=%s collection_status=%s "
            "analytics_status=skipped",
            summary.run_id,
            summary.collection_status,
        )
        return replace(summary, analytics_status="skipped")

    try:
        report_path = analytics_runner().resolve()
    except Exception as exc:
        error_message = _safe_error_message(exc, None)
        logger.exception(
            "Daily pipeline analytics failed run_id=%s collection_status=%s "
            "analytics_status=failed error=%s",
            summary.run_id,
            summary.collection_status,
            error_message,
        )
        return replace(
            summary,
            analytics_status="failed",
            analytics_error_message=error_message,
        )

    logger.info(
        "Daily pipeline completed run_id=%s collection_status=%s "
        "analytics_status=completed analytics_report_path=%s",
        summary.run_id,
        summary.collection_status,
        report_path,
    )
    return replace(
        summary,
        analytics_status="completed",
        analytics_report_path=str(report_path),
    )


def generate_daily_run_id(run_date: date) -> str:
    """Generate a filesystem-safe unique run ID containing the logical date."""

    return f"daily-{run_date:%Y%m%d}-{uuid4().hex[:10]}"


def validate_daily_run_id(run_id: str) -> str:
    """Validate a run ID for both collection keys and Windows directories."""

    normalized = validate_collection_run_id(run_id)
    if _FILESYSTEM_RUN_ID_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "daily run_id must use letters, digits, '.', '_', or '-' so it is "
            "safe as a Windows directory name"
        )
    return normalized


def reserve_run_output_directory(
    raw_output_root: Path,
    *,
    run_date: date,
    run_id: str,
) -> Path:
    """Create a new immutable run directory and reject accidental reuse."""

    run_root = raw_output_root / run_date.isoformat() / validate_daily_run_id(run_id)
    try:
        run_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"raw output directory already exists for run_id={run_id}: {run_root}"
        ) from exc
    return run_root


def database_url_from_path(database_path: Path) -> str:
    """Return a SQLite URL for an existing database file."""

    resolved_path = database_path.expanduser().resolve()
    if not resolved_path.is_file():
        raise ValueError(f"database path must be an existing file: {resolved_path}")
    return f"sqlite+pysqlite:///{resolved_path.as_posix()}"


def main() -> int:
    """Run collection and, only after success, generate daily intelligence."""

    arguments = _parse_arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_date = arguments.run_date or datetime.now(UTC).date()
    run_id = arguments.run_id or generate_daily_run_id(run_date)
    entry_started_at = datetime.now(UTC)
    logger.info(
        "Daily pipeline starting run_id=%s collection_status=running "
        "analytics_status=not_started",
        run_id,
    )
    engine = None
    try:
        database_url = (
            database_url_from_path(arguments.database_path)
            if arguments.database_path is not None
            else arguments.database_url
        )
        tasks = load_collection_tasks(arguments.config)
        engine = create_database_engine(database_url)
        session_factory = create_session_factory(engine)

        def run_cohort(
            cohort_tasks: tuple[CollectionTask, ...],
            raw_html_dir: Path,
            shared_run_id: str,
        ) -> AutoScout24MultiModelCollectionResult:
            with session_scope(session_factory) as session:
                return AutoScout24MultiModelCollectionPipeline(
                    AutoScout24Collector(),
                    session,
                ).run(
                    cohort_tasks,
                    raw_html_dir=raw_html_dir,
                    mode="import",
                    run_id=shared_run_id,
                )

        summary = run_daily_market_monitor(
            tasks,
            raw_output_root=arguments.raw_output_root,
            run_date=run_date,
            run_id=run_id,
            cohort_runner=run_cohort,
        )
        logger.info(
            "Daily collection finished run_id=%s collection_status=%s "
            "analytics_status=not_started",
            summary.run_id,
            summary.collection_status,
        )

        def run_analytics() -> Path:
            with session_factory() as session:
                report = build_daily_market_intelligence(
                    session,
                    report_date=run_date,
                )
            return write_daily_market_intelligence(
                report,
                arguments.analytics_output,
            )

        summary = run_analytics_after_collection(
            summary,
            analytics_runner=run_analytics,
        )
    except Exception as exc:
        error_message = _safe_error_message(exc, arguments.database_url)
        logger.error(
            "Daily market monitor failed before producing a run summary "
            "collection_status=failed analytics_status=skipped error=%s",
            error_message,
        )
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_date": run_date.isoformat(),
                    "started_at": entry_started_at.isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "status": "failed",
                    "collection_status": "failed",
                    "analytics_status": "skipped",
                    "analytics_report_path": None,
                    "analytics_error_message": None,
                    "successful_cohorts": 0,
                    "failed_cohorts": len(DEFAULT_COHORTS),
                    "listings_inserted": 0,
                    "observations_inserted": 0,
                    "price_history_inserted": 0,
                    "cohorts": [],
                    "error_message": error_message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    finally:
        if engine is not None:
            engine.dispose()

    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0 if summary.status == "completed" else 1


def _run_cohort(
    cohort: str,
    cohort_tasks: tuple[CollectionTask, ...],
    *,
    cohort_output_dir: Path,
    run_id: str,
    cohort_runner: CohortRunner,
) -> DailyCohortSummary:
    if not cohort_tasks:
        return _failed_cohort_summary(
            cohort,
            cohort_output_dir,
            "No enabled tasks configured for cohort",
            tasks=(),
        )

    try:
        result = cohort_runner(cohort_tasks, cohort_output_dir, run_id)
        if result.run_id != run_id:
            raise ValueError(
                "cohort result run_id does not match the daily runner: "
                f"expected={run_id} actual={result.run_id}"
            )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.exception("Daily collection cohort failed cohort=%s", cohort)
        return _failed_cohort_summary(
            cohort,
            cohort_output_dir,
            error_message,
            tasks=cohort_tasks,
        )

    task_failures = tuple(
        FailedTaskSummary(
            task_id=task.task_id,
            error_message=task.error_message or "Task did not complete successfully",
        )
        for task in result.tasks
        if not task.succeeded or task.failed_pages > 0
    )
    if result.failed_tasks == 0 and result.failed_pages == 0:
        status = "completed"
    elif result.succeeded_tasks == 0:
        status = "failed"
    else:
        status = "partially_completed"
    return DailyCohortSummary(
        cohort=cohort,
        status=status,
        raw_html_dir=str(cohort_output_dir),
        requested_tasks=result.requested_tasks,
        succeeded_tasks=result.succeeded_tasks,
        failed_tasks=result.failed_tasks,
        listings_inserted=result.inserted,
        observations_inserted=result.observations_inserted,
        price_history_inserted=result.price_history_inserted,
        task_failures=task_failures,
    )


def _failed_cohort_summary(
    cohort: str,
    cohort_output_dir: Path,
    error_message: str,
    *,
    tasks: tuple[CollectionTask, ...],
) -> DailyCohortSummary:
    return DailyCohortSummary(
        cohort=cohort,
        status="failed",
        raw_html_dir=str(cohort_output_dir),
        requested_tasks=len(tasks),
        succeeded_tasks=0,
        failed_tasks=len(tasks),
        listings_inserted=0,
        observations_inserted=0,
        price_history_inserted=0,
        task_failures=tuple(
            FailedTaskSummary(task_id=task.task_id, error_message=error_message)
            for task in tasks
        ),
        error_message=error_message,
    )


def _overall_status(cohorts: list[DailyCohortSummary]) -> str:
    completed = sum(cohort.status == "completed" for cohort in cohorts)
    if completed == len(cohorts):
        return "completed"
    if completed == 0 and all(cohort.status == "failed" for cohort in cohorts):
        return "failed"
    return "partially_completed"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run core_a and core_b daily collection cohorts, then generate "
            "market intelligence after complete success."
        ),
    )
    database_group = parser.add_mutually_exclusive_group()
    database_group.add_argument("--database-url")
    database_group.add_argument("--database-path", type=Path)
    parser.add_argument("--date", dest="run_date", type=_parse_date)
    parser.add_argument("--run-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--raw-output-root",
        type=Path,
        default=DEFAULT_RAW_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--analytics-output",
        type=Path,
        default=DEFAULT_ANALYTICS_OUTPUT,
    )
    return parser.parse_args()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_error_message(exc: Exception, database_url: str | None) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if database_url:
        message = message.replace(database_url, "<redacted-database-url>")
    return message


if __name__ == "__main__":
    raise SystemExit(main())
