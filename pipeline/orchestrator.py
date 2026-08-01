"""Collection → Analytics → AI → Strategic orchestration with stage gates."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ai.pipeline import AIStageResult, run_ai_report_stage
from external_intelligence.content_feed import (
    ContentFeedResult,
    build_content_feed,
)
from external_intelligence.pipeline import (
    ExternalIntelligenceStageResult,
    run_external_intelligence_stage,
)
from pipeline.models import PipelineRunResult, PipelineStatus, PipelineTimestamps
from pipeline.storage import archive_existing_artifacts, write_pipeline_status
from strategic.pipeline import StrategicStageResult, run_strategic_report_stage

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAILY_MONITOR = PROJECT_ROOT / "scripts" / "daily_market_monitor.py"
DEFAULT_ANALYTICS_REPORT = Path("reports/daily_market_intelligence.json")
DEFAULT_AI_REPORT = Path("reports/daily_ai_market_report.md")
DEFAULT_EXTERNAL_INTELLIGENCE_REPORT = Path("reports/external_intelligence.json")
DEFAULT_CONTENT_FEED_REPORT = Path("reports/external_intelligence/content_feed.json")
DEFAULT_STRATEGIC_REPORT = Path("reports/strategic_market_report.md")
DEFAULT_STATUS_OUTPUT = Path("reports/pipeline_status.json")
DEFAULT_ARCHIVE_ROOT = Path("reports/archive")


class AIRunner(Protocol):
    """Injectable AI stage callable used by deterministic tests."""

    def __call__(
        self,
        *,
        analytics_status: str,
        input_path: str | Path,
        output_path: str | Path,
    ) -> AIStageResult: ...


class StrategicRunner(Protocol):
    """Injectable strategic stage callable used by deterministic tests."""

    def __call__(
        self,
        *,
        analytics_input_path: str | Path,
        ai_input_path: str | Path,
        external_input_path: str | Path,
        output_path: str | Path,
    ) -> StrategicStageResult: ...


class ExternalIntelligenceRunner(Protocol):
    """Injectable external-intelligence stage callable."""

    def __call__(
        self,
        *,
        analytics_input_path: str | Path,
        output_path: str | Path,
    ) -> ExternalIntelligenceStageResult: ...


class ContentFeedRunner(Protocol):
    """Injectable content-feed stage callable."""

    def __call__(
        self,
        *,
        external_input: str | Path,
        analytics_input: str | Path,
        output_path: str | Path,
    ) -> ContentFeedResult: ...


SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], datetime]
PipelineIDFactory = Callable[[], str]


def run_intelligence_pipeline(
    collection_args: Sequence[str],
    *,
    analytics_report_path: str | Path = DEFAULT_ANALYTICS_REPORT,
    ai_report_path: str | Path = DEFAULT_AI_REPORT,
    external_intelligence_report_path: str | Path = (
        DEFAULT_EXTERNAL_INTELLIGENCE_REPORT
    ),
    content_feed_report_path: str | Path = DEFAULT_CONTENT_FEED_REPORT,
    strategic_report_path: str | Path = DEFAULT_STRATEGIC_REPORT,
    status_output_path: str | Path = DEFAULT_STATUS_OUTPUT,
    archive_root: str | Path = DEFAULT_ARCHIVE_ROOT,
    subprocess_runner: SubprocessRunner = subprocess.run,
    ai_runner: AIRunner = run_ai_report_stage,
    external_intelligence_runner: ExternalIntelligenceRunner = (
        run_external_intelligence_stage
    ),
    content_feed_runner: ContentFeedRunner = build_content_feed,
    strategic_runner: StrategicRunner = run_strategic_report_stage,
    clock: Clock | None = None,
    pipeline_id_factory: PipelineIDFactory | None = None,
) -> PipelineRunResult:
    """Run all intelligence stages sequentially with failure isolation."""

    _validate_collection_args(collection_args)
    active_clock = clock or _utc_now
    pipeline_id = (pipeline_id_factory or _new_pipeline_id)()
    analytics_path = _resolve(analytics_report_path)
    ai_path = _resolve(ai_report_path)
    external_path = _resolve(external_intelligence_report_path)
    content_feed_path = _resolve(content_feed_report_path)
    strategic_path = _resolve(strategic_report_path)
    status_path = _resolve(status_output_path)
    archive_root_path = _resolve(archive_root)
    status = PipelineStatus(
        pipeline_id=pipeline_id,
        pipeline_status="initializing",
        run_id=None,
        collection_exit_code=None,
        collection_status="not_started",
        analytics_status="not_started",
        ai_status="not_started",
        external_intelligence_status="not_started",
        content_feed_status="not_started",
        strategic_status="not_started",
        timestamps=PipelineTimestamps(
            pipeline_started_at=_timestamp(active_clock),
        ),
        report_paths={
            "analytics": str(analytics_path),
            "ai": str(ai_path),
            "external_intelligence": str(external_path),
            "content_feed": str(content_feed_path),
            "strategic": str(strategic_path),
            "pipeline_status": str(status_path),
        },
        archive_path=None,
        errors={},
    )

    try:
        archive_path = archive_existing_artifacts(
            pipeline_id=pipeline_id,
            archive_root=archive_root_path,
            artifacts={
                "analytics": analytics_path,
                "ai": ai_path,
                "external_intelligence": external_path,
                "content_feed": content_feed_path,
                "strategic": strategic_path,
                "pipeline_status": status_path,
            },
        )
    except Exception as exc:
        status = _fatal_status(status, "archive", exc, active_clock)
        status = replace(
            status,
            collection_status="skipped",
            analytics_status="skipped",
            ai_status="skipped",
            external_intelligence_status="skipped",
            content_feed_status="skipped",
            strategic_status="skipped",
        )
        if not status_path.exists():
            _best_effort_status_write(status, status_path)
        return PipelineRunResult(status, None, "", "")

    status = replace(
        status,
        pipeline_status="running",
        archive_path=str(archive_path),
        timestamps=replace(
            status.timestamps,
            archive_completed_at=_timestamp(active_clock),
            collection_started_at=_timestamp(active_clock),
        ),
        collection_status="running",
    )
    write_pipeline_status(status, status_path)

    try:
        completed = subprocess_runner(
            [
                sys.executable,
                str(DAILY_MONITOR),
                *collection_args,
                "--analytics-output",
                str(analytics_path),
            ],
            cwd=PROJECT_ROOT,
            env=_subprocess_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        status = _fatal_status(status, "collection", exc, active_clock)
        status = replace(
            status,
            collection_status="failed",
            analytics_status="skipped",
            ai_status="skipped",
            external_intelligence_status="skipped",
            content_feed_status="skipped",
            strategic_status="skipped",
            timestamps=replace(
                status.timestamps,
                collection_completed_at=_timestamp(active_clock),
                pipeline_completed_at=_timestamp(active_clock),
            ),
        )
        write_pipeline_status(status, status_path)
        return PipelineRunResult(status, None, "", str(exc))

    payload, parse_error = _daily_monitor_payload(completed.stdout)
    stage_end = _timestamp(active_clock)
    if payload is None:
        errors = {**status.errors, "collection": parse_error or "Unknown error"}
        status = replace(
            status,
            pipeline_status="failed",
            collection_exit_code=completed.returncode,
            collection_status="failed",
            analytics_status="skipped",
            ai_status="skipped",
            external_intelligence_status="skipped",
            content_feed_status="skipped",
            strategic_status="skipped",
            errors=errors,
            timestamps=replace(
                status.timestamps,
                collection_completed_at=stage_end,
                pipeline_completed_at=stage_end,
            ),
        )
        write_pipeline_status(status, status_path)
        return PipelineRunResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )

    collection_status = _status_text(payload, "collection_status")
    analytics_status = _status_text(payload, "analytics_status")
    errors = dict(status.errors)
    _capture_payload_error(payload, collection_status, analytics_status, errors)
    if completed.returncode != 0 and collection_status == "completed":
        collection_status = "failed"
        analytics_status = "skipped"
        errors["collection"] = (
            "Daily monitor returned a non-zero exit code despite completed status: "
            f"{completed.returncode}"
        )
    status = replace(
        status,
        run_id=_optional_text(payload.get("run_id")),
        collection_exit_code=completed.returncode,
        collection_status=collection_status,
        analytics_status=analytics_status,
        errors=errors,
        timestamps=replace(
            status.timestamps,
            collection_completed_at=stage_end,
            analytics_started_at=(
                stage_end if analytics_status in {"completed", "failed"} else None
            ),
            analytics_completed_at=(
                stage_end if analytics_status in {"completed", "failed"} else None
            ),
        ),
    )
    write_pipeline_status(status, status_path)

    if collection_status != "completed" or analytics_status != "completed":
        status = _finish_skipped_downstream(status, active_clock)
        write_pipeline_status(status, status_path)
        return PipelineRunResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )

    status = replace(
        status,
        ai_status="running",
        timestamps=replace(
            status.timestamps,
            ai_started_at=_timestamp(active_clock),
        ),
    )
    write_pipeline_status(status, status_path)
    try:
        ai_result = ai_runner(
            analytics_status="completed",
            input_path=analytics_path,
            output_path=ai_path,
        )
    except Exception as exc:
        ai_result = AIStageResult(
            analytics_status="completed",
            ai_status="failed",
            input_path=str(analytics_path),
            output_path=None,
            generation_mode=None,
            provider_name=None,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    ai_end = _timestamp(active_clock)
    errors = dict(status.errors)
    if ai_result.error_message:
        errors["ai"] = ai_result.error_message
    status = replace(
        status,
        ai_status=ai_result.ai_status,
        errors=errors,
        timestamps=replace(status.timestamps, ai_completed_at=ai_end),
    )
    write_pipeline_status(status, status_path)
    if ai_result.ai_status != "completed":
        status = replace(
            status,
            pipeline_status="failed",
            external_intelligence_status="skipped",
            content_feed_status="skipped",
            strategic_status="skipped",
            timestamps=replace(
                status.timestamps,
                pipeline_completed_at=_timestamp(active_clock),
            ),
        )
        write_pipeline_status(status, status_path)
        return PipelineRunResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )

    status = replace(
        status,
        external_intelligence_status="running",
        timestamps=replace(
            status.timestamps,
            external_intelligence_started_at=_timestamp(active_clock),
        ),
    )
    write_pipeline_status(status, status_path)
    try:
        external_result = external_intelligence_runner(
            analytics_input_path=analytics_path,
            output_path=external_path,
        )
    except Exception as exc:
        external_result = ExternalIntelligenceStageResult(
            external_intelligence_status="failed",
            analytics_input_path=str(analytics_path),
            output_path=None,
            signal_count=0,
            available_source_count=0,
            failed_source_count=0,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    external_end = _timestamp(active_clock)
    errors = dict(status.errors)
    if external_result.error_message:
        errors["external_intelligence"] = external_result.error_message
    status = replace(
        status,
        external_intelligence_status=(external_result.external_intelligence_status),
        errors=errors,
        timestamps=replace(
            status.timestamps,
            external_intelligence_completed_at=external_end,
        ),
    )
    write_pipeline_status(status, status_path)
    if not _usable_stage(status.external_intelligence_status):
        status = replace(
            status,
            pipeline_status="failed",
            content_feed_status="skipped",
            strategic_status="skipped",
            timestamps=replace(
                status.timestamps,
                pipeline_completed_at=_timestamp(active_clock),
            ),
        )
        write_pipeline_status(status, status_path)
        return PipelineRunResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )

    status = replace(
        status,
        content_feed_status="running",
        timestamps=replace(
            status.timestamps,
            content_feed_started_at=_timestamp(active_clock),
        ),
    )
    write_pipeline_status(status, status_path)
    try:
        content_result = content_feed_runner(
            external_input=external_path,
            analytics_input=analytics_path,
            output_path=content_feed_path,
        )
    except Exception as exc:
        content_result = ContentFeedResult(
            status="failed",
            output_path=None,
            news_count=0,
            report_count=0,
            video_count=0,
            source_statuses=(),
            error_message=f"{type(exc).__name__}: {exc}",
        )
    content_status = _content_status(content_result)
    content_end = _timestamp(active_clock)
    errors = dict(status.errors)
    if content_result.error_message:
        errors["content_feed"] = content_result.error_message
    elif content_status == "partially_completed":
        failed_sources = sum(
            source.get("status") == "failed"
            for source in content_result.source_statuses
        )
        errors["content_feed"] = (
            f"{failed_sources} content source(s) failed; see source limitations "
            "in reports/external_intelligence/content_feed.json"
        )
    status = replace(
        status,
        content_feed_status=content_status,
        errors=errors,
        timestamps=replace(
            status.timestamps,
            content_feed_completed_at=content_end,
        ),
    )
    write_pipeline_status(status, status_path)
    if not _usable_stage(content_status):
        status = replace(
            status,
            pipeline_status="failed",
            strategic_status="skipped",
            timestamps=replace(
                status.timestamps,
                pipeline_completed_at=_timestamp(active_clock),
            ),
        )
        write_pipeline_status(status, status_path)
        return PipelineRunResult(
            status,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )

    status = replace(
        status,
        strategic_status="running",
        timestamps=replace(
            status.timestamps,
            strategic_started_at=_timestamp(active_clock),
        ),
    )
    write_pipeline_status(status, status_path)
    try:
        strategic_result = strategic_runner(
            analytics_input_path=analytics_path,
            ai_input_path=ai_path,
            external_input_path=external_path,
            output_path=strategic_path,
        )
    except Exception as exc:
        strategic_result = StrategicStageResult(
            strategic_status="failed",
            analytics_input_path=str(analytics_path),
            ai_input_path=str(ai_path),
            output_path=None,
            external_signal_count=0,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    errors = dict(status.errors)
    if strategic_result.error_message:
        errors["strategic"] = strategic_result.error_message
    strategic_end = _timestamp(active_clock)
    strategic_status = strategic_result.strategic_status
    status = replace(
        status,
        pipeline_status=_final_pipeline_status(status, strategic_status),
        strategic_status=strategic_status,
        errors=errors,
        timestamps=replace(
            status.timestamps,
            strategic_completed_at=strategic_end,
            pipeline_completed_at=strategic_end,
        ),
    )
    write_pipeline_status(status, status_path)
    return PipelineRunResult(
        status,
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def _finish_skipped_downstream(
    status: PipelineStatus,
    clock: Clock,
) -> PipelineStatus:
    return replace(
        status,
        pipeline_status="failed",
        ai_status="skipped",
        external_intelligence_status="skipped",
        content_feed_status="skipped",
        strategic_status="skipped",
        timestamps=replace(
            status.timestamps,
            pipeline_completed_at=_timestamp(clock),
        ),
    )


def _usable_stage(status: str) -> bool:
    return status in {"completed", "partially_completed"}


def _content_status(result: ContentFeedResult) -> str:
    if result.status != "completed":
        return result.status
    if any(source.get("status") == "failed" for source in result.source_statuses):
        return "partially_completed"
    return "completed"


def _final_pipeline_status(status: PipelineStatus, strategic_status: str) -> str:
    if strategic_status != "completed":
        return "failed"
    if "partially_completed" in {
        status.external_intelligence_status,
        status.content_feed_status,
    }:
        return "partially_completed"
    return "completed"


def _fatal_status(
    status: PipelineStatus,
    stage: str,
    exc: Exception,
    clock: Clock,
) -> PipelineStatus:
    return replace(
        status,
        pipeline_status="failed",
        errors={**status.errors, stage: f"{type(exc).__name__}: {exc}"},
        timestamps=replace(
            status.timestamps,
            pipeline_completed_at=_timestamp(clock),
        ),
    )


def _best_effort_status_write(status: PipelineStatus, path: Path) -> None:
    try:
        write_pipeline_status(status, path)
    except OSError:
        logger.exception("Could not persist fatal pipeline status path=%s", path)


def _capture_payload_error(
    payload: dict[str, Any],
    collection_status: str,
    analytics_status: str,
    errors: dict[str, str],
) -> None:
    if collection_status != "completed":
        errors["collection"] = _optional_text(payload.get("error_message")) or (
            f"Daily monitor collection status: {collection_status}"
        )
    if analytics_status == "failed":
        errors["analytics"] = (
            _optional_text(payload.get("analytics_error_message"))
            or "Analytics stage failed without an error message"
        )
    elif analytics_status not in {"completed", "skipped"}:
        errors["analytics"] = f"Daily monitor analytics status: {analytics_status}"


def _daily_monitor_payload(
    stdout: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"Daily monitor summary is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "Daily monitor summary must be a JSON object"
    return payload, None


def _status_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else "unknown"


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _validate_collection_args(collection_args: Sequence[str]) -> None:
    if any(
        argument == "--analytics-output" or argument.startswith("--analytics-output=")
        for argument in collection_args
    ):
        raise ValueError(
            "--analytics-output is controlled by the pipeline orchestration layer"
        )


def _subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(PROJECT_ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else source_root
    )
    return environment


def _resolve(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve(strict=False)


def _timestamp(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_pipeline_id() -> str:
    now = datetime.now(UTC)
    return f"pipeline-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:10]}"
