"""Tests for end-to-end stage gating, archives, and status transitions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai.pipeline import AIStageResult
from external_intelligence.content_feed import ContentFeedResult
from external_intelligence.pipeline import ExternalIntelligenceStageResult
from pipeline.executive_brief import ExecutiveBriefStageResult
from pipeline.orchestrator import run_intelligence_pipeline
from pipeline.tests.helpers import StepClock, daily_summary, write_analytics
from strategic.pipeline import StrategicStageResult


def test_success_runs_all_stages_and_archives_prior_versions(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        analytics_output = Path(command[command.index("--analytics-output") + 1])
        write_analytics(analytics_output)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=daily_summary(),
            stderr="daily monitor log\n",
        )

    result = run_intelligence_pipeline(
        ["--database-path", "fixture.sqlite3"],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=_successful_external,
        content_feed_runner=_successful_content_feed,
        executive_brief_runner=_successful_executive_brief,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-success",
    )

    status = result.status
    assert status.pipeline_status == "completed"
    assert status.collection_status == "completed"
    assert status.analytics_status == "completed"
    assert status.ai_status == "completed"
    assert status.external_intelligence_status == "completed"
    assert status.content_feed_status == "completed"
    assert status.executive_brief_status == "completed"
    assert status.executive_brief_error_message is None
    assert status.strategic_status == "completed"
    assert status.run_id == "daily-fixture-run"
    assert status.collection_exit_code == 0
    assert result.collection_stderr == "daily monitor log\n"
    assert "AI-powered German Automotive Market Report" in paths[
        "ai_report_path"
    ].read_text(encoding="utf-8")
    assert "Strategic Market Report" in paths["strategic_report_path"].read_text(
        encoding="utf-8"
    )
    assert paths["executive_brief_report_path"].read_text(encoding="utf-8") == (
        "new executive brief"
    )
    persisted = json.loads(paths["status_output_path"].read_text(encoding="utf-8"))
    assert persisted["executive_brief_status"] == "completed"
    assert persisted["executive_brief_error_message"] is None
    assert persisted["strategic_status"] == "completed"
    assert all(value is not None for value in persisted["timestamps"].values())

    archive = paths["archive_root"] / "pipeline-success"
    assert (archive / "daily_market_intelligence.json").read_text(
        encoding="utf-8"
    ) == "old analytics"
    assert (archive / "daily_ai_market_report.md").read_text(
        encoding="utf-8"
    ) == "old ai"
    assert (archive / "strategic_market_report.md").read_text(
        encoding="utf-8"
    ) == "old strategic"
    assert (archive / "external_intelligence.json").read_text(
        encoding="utf-8"
    ) == "old external"
    assert (archive / "content_feed.json").read_text(encoding="utf-8") == "old content"
    assert (archive / "daily_executive_intelligence_brief.md").read_text(
        encoding="utf-8"
    ) == "old executive brief"
    assert (archive / "pipeline_status.json").read_text(
        encoding="utf-8"
    ) == "old status"


@pytest.mark.parametrize(
    ("collection_status", "analytics_status", "returncode"),
    (("failed", "skipped", 2), ("completed", "failed", 0)),
)
def test_collection_or_analytics_failure_skips_downstream_and_preserves_reports(
    tmp_path: Path,
    collection_status: str,
    analytics_status: str,
    returncode: int,
) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=daily_summary(
                collection_status=collection_status,
                analytics_status=analytics_status,
            ),
            stderr="failed daily log",
        )

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        clock=StepClock(),
        pipeline_id_factory=lambda: f"pipeline-{collection_status}-{analytics_status}",
    )

    assert result.status.pipeline_status == "failed"
    assert result.status.collection_status == collection_status
    assert result.status.analytics_status == analytics_status
    assert result.status.ai_status == "skipped"
    assert result.status.external_intelligence_status == "skipped"
    assert result.status.content_feed_status == "skipped"
    assert result.status.executive_brief_status == "skipped"
    assert result.status.strategic_status == "skipped"
    assert paths["ai_report_path"].read_text(encoding="utf-8") == "old ai"
    assert paths["strategic_report_path"].read_text(encoding="utf-8") == "old strategic"


def test_ai_failure_skips_strategy_and_preserves_old_downstream_reports(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)
    strategic_called = False

    def daily_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def failed_ai(**kwargs: object) -> AIStageResult:
        del kwargs
        return AIStageResult(
            analytics_status="completed",
            ai_status="failed",
            input_path="analytics.json",
            output_path=None,
            generation_mode=None,
            provider_name=None,
            error_message="fixture AI failure",
        )

    def forbidden_strategy(**kwargs: object) -> StrategicStageResult:
        nonlocal strategic_called
        del kwargs
        strategic_called = True
        raise AssertionError("Strategic stage must be skipped")

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        ai_runner=failed_ai,
        strategic_runner=forbidden_strategy,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-ai-failed",
    )

    assert result.status.ai_status == "failed"
    assert result.status.external_intelligence_status == "skipped"
    assert result.status.content_feed_status == "skipped"
    assert result.status.executive_brief_status == "skipped"
    assert result.status.strategic_status == "skipped"
    assert strategic_called is False
    assert paths["ai_report_path"].read_text(encoding="utf-8") == "old ai"
    assert paths["strategic_report_path"].read_text(encoding="utf-8") == "old strategic"


def test_strategic_failure_preserves_old_strategic_report(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def failed_strategy(**kwargs: object) -> StrategicStageResult:
        del kwargs
        return StrategicStageResult(
            strategic_status="failed",
            analytics_input_path="analytics.json",
            ai_input_path="ai.md",
            output_path=None,
            external_signal_count=0,
            error_message="fixture strategic failure",
        )

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=_successful_external,
        content_feed_runner=_successful_content_feed,
        executive_brief_runner=_successful_executive_brief,
        strategic_runner=failed_strategy,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-strategic-failed",
    )

    assert result.status.ai_status == "completed"
    assert result.status.strategic_status == "failed"
    assert result.status.pipeline_status == "failed"
    assert paths["strategic_report_path"].read_text(encoding="utf-8") == "old strategic"


def test_invalid_daily_summary_fails_without_touching_reports(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-invalid-summary",
    )

    assert result.status.collection_status == "failed"
    assert result.status.analytics_status == "skipped"
    assert result.status.ai_status == "skipped"
    assert "not valid JSON" in result.status.errors["collection"]
    assert paths["analytics_report_path"].read_text(encoding="utf-8") == "old analytics"


def test_external_failure_skips_content_and_strategy_and_preserves_artifacts(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def failed_external(**kwargs: object) -> ExternalIntelligenceStageResult:
        del kwargs
        return ExternalIntelligenceStageResult(
            external_intelligence_status="failed",
            analytics_input_path="analytics.json",
            output_path=None,
            signal_count=0,
            available_source_count=0,
            failed_source_count=3,
            error_message="fixture external failure",
        )

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=failed_external,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-external-failed",
    )

    assert result.status.external_intelligence_status == "failed"
    assert result.status.content_feed_status == "skipped"
    assert result.status.executive_brief_status == "skipped"
    assert result.status.strategic_status == "skipped"
    assert (
        paths["external_intelligence_report_path"].read_text(encoding="utf-8")
        == "old external"
    )
    assert paths["content_feed_report_path"].read_text(encoding="utf-8") == (
        "old content"
    )


def test_content_failure_skips_strategy_and_preserves_old_feed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def failed_content(**kwargs: object) -> ContentFeedResult:
        del kwargs
        return ContentFeedResult(
            status="failed",
            output_path=None,
            news_count=0,
            report_count=0,
            video_count=0,
            source_statuses=(),
            error_message="fixture content failure",
        )

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=_successful_external,
        content_feed_runner=failed_content,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-content-failed",
    )

    assert result.status.external_intelligence_status == "completed"
    assert result.status.content_feed_status == "failed"
    assert result.status.executive_brief_status == "skipped"
    assert result.status.strategic_status == "skipped"
    assert paths["content_feed_report_path"].read_text(encoding="utf-8") == (
        "old content"
    )


def test_partial_sources_are_recorded_and_allow_strategy(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def daily_runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def partial_external(**kwargs: object) -> ExternalIntelligenceStageResult:
        result = _successful_external(**kwargs)
        return ExternalIntelligenceStageResult(
            external_intelligence_status="partially_completed",
            analytics_input_path=result.analytics_input_path,
            output_path=result.output_path,
            signal_count=result.signal_count,
            available_source_count=2,
            failed_source_count=1,
            error_message="1 external source failed",
        )

    def partial_content(**kwargs: object) -> ContentFeedResult:
        result = _successful_content_feed(**kwargs)
        return ContentFeedResult(
            status=result.status,
            output_path=result.output_path,
            news_count=result.news_count,
            report_count=result.report_count,
            video_count=result.video_count,
            source_statuses=({"status": "failed"}, {"status": "available"}),
        )

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=partial_external,
        content_feed_runner=partial_content,
        executive_brief_runner=_successful_executive_brief,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-partial",
    )

    assert result.status.pipeline_status == "partially_completed"
    assert result.status.executive_brief_status == "completed"
    assert result.status.strategic_status == "completed"
    assert result.status.errors["external_intelligence"] == ("1 external source failed")
    assert "1 content source(s) failed" in result.status.errors["content_feed"]


def test_executive_brief_failure_isolated_and_preserves_old_brief(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)

    def daily_runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        write_analytics(Path(command[command.index("--analytics-output") + 1]))
        return subprocess.CompletedProcess(command, 0, daily_summary(), "")

    def failed_executive_brief(**kwargs: object) -> ExecutiveBriefStageResult:
        del kwargs
        raise RuntimeError("fixture brief failure")

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=daily_runner,
        external_intelligence_runner=_successful_external,
        content_feed_runner=_successful_content_feed,
        executive_brief_runner=failed_executive_brief,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-executive-brief-failed",
    )

    assert result.status.collection_status == "completed"
    assert result.status.analytics_status == "completed"
    assert result.status.executive_brief_status == "failed"
    assert result.status.strategic_status == "completed"
    assert result.status.pipeline_status == "partially_completed"
    assert result.status.executive_brief_error_message == (
        "RuntimeError: fixture brief failure"
    )
    assert result.status.errors["executive_brief"] == (
        "RuntimeError: fixture brief failure"
    )
    assert result.status.timestamps.executive_brief_started_at is not None
    assert result.status.timestamps.executive_brief_completed_at is not None
    assert paths["executive_brief_report_path"].read_text(encoding="utf-8") == (
        "old executive brief"
    )


def test_pipeline_controls_analytics_output_argument(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    with pytest.raises(ValueError, match="controlled by the pipeline"):
        run_intelligence_pipeline(
            ["--analytics-output", "other.json"],
            **paths,
            clock=StepClock(),
            pipeline_id_factory=lambda: "pipeline-invalid-args",
        )


def test_archive_failure_stops_before_collection_and_preserves_old_status(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_old_artifacts(paths)
    duplicate_archive = paths["archive_root"] / "pipeline-duplicate"
    duplicate_archive.mkdir(parents=True)
    collection_called = False

    def forbidden_collection(*args: object, **kwargs: object) -> None:
        nonlocal collection_called
        del args, kwargs
        collection_called = True

    result = run_intelligence_pipeline(
        [],
        **paths,
        subprocess_runner=forbidden_collection,
        clock=StepClock(),
        pipeline_id_factory=lambda: "pipeline-duplicate",
    )

    assert result.status.pipeline_status == "failed"
    assert result.status.collection_status == "skipped"
    assert result.status.analytics_status == "skipped"
    assert collection_called is False
    assert paths["status_output_path"].read_text(encoding="utf-8") == "old status"


def _paths(tmp_path: Path) -> dict[str, Path]:
    reports = tmp_path / "reports"
    return {
        "analytics_report_path": reports / "daily_market_intelligence.json",
        "ai_report_path": reports / "daily_ai_market_report.md",
        "external_intelligence_report_path": reports / "external_intelligence.json",
        "content_feed_report_path": reports
        / "external_intelligence"
        / "content_feed.json",
        "executive_brief_report_path": (
            reports / "daily_executive_intelligence_brief.md"
        ),
        "strategic_report_path": reports / "strategic_market_report.md",
        "status_output_path": reports / "pipeline_status.json",
        "archive_root": reports / "archive",
    }


def _write_old_artifacts(paths: dict[str, Path]) -> None:
    values = {
        "analytics_report_path": "old analytics",
        "ai_report_path": "old ai",
        "external_intelligence_report_path": "old external",
        "content_feed_report_path": "old content",
        "executive_brief_report_path": "old executive brief",
        "strategic_report_path": "old strategic",
        "status_output_path": "old status",
    }
    for key, value in values.items():
        path = paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def _successful_external(
    *,
    analytics_input_path: str | Path,
    output_path: str | Path,
) -> ExternalIntelligenceStageResult:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_date": "2026-07-31",
                "generated_at": "2026-07-31T18:00:00+00:00",
                "kba": {
                    "status": "failed",
                    "provider": "fixture-kba",
                    "records": [],
                    "limitations": ["fixture unavailable"],
                },
                "news": {
                    "status": "available",
                    "provider": "fixture-news",
                    "articles": [
                        {
                            "article_id": "fixture-news-1",
                            "title": "Fixture market signal",
                            "summary": "Attributed fixture summary.",
                            "url": "https://example.test/news",
                            "published_at": "2026-07-30T08:00:00+00:00",
                            "brands": ["Dynamic Motors"],
                            "models": ["Dynamic Motors Alpha"],
                        }
                    ],
                    "limitations": [],
                },
                "brand_news": {
                    "status": "available",
                    "provider": "fixture-brand-news",
                    "articles": [],
                    "limitations": [],
                },
                "sources": [],
            }
        ),
        encoding="utf-8",
    )
    return ExternalIntelligenceStageResult(
        external_intelligence_status="completed",
        analytics_input_path=str(analytics_input_path),
        output_path=str(output),
        signal_count=1,
        available_source_count=1,
        failed_source_count=0,
    )


def _successful_content_feed(
    *,
    external_input: str | Path,
    analytics_input: str | Path,
    output_path: str | Path,
) -> ContentFeedResult:
    del external_input, analytics_input
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('{"items": []}', encoding="utf-8")
    return ContentFeedResult(
        status="completed",
        output_path=str(output),
        news_count=0,
        report_count=0,
        video_count=0,
        source_statuses=(),
    )


def _successful_executive_brief(
    *,
    analytics_status: str,
    ai_status: str,
    external_intelligence_status: str,
    content_feed_status: str,
    analytics_input_path: str | Path,
    ai_input_path: str | Path,
    external_input_path: str | Path,
    content_feed_input_path: str | Path,
    output_path: str | Path,
) -> ExecutiveBriefStageResult:
    assert analytics_status == "completed"
    assert ai_status == "completed"
    assert external_intelligence_status in {"completed", "partially_completed"}
    assert content_feed_status in {"completed", "partially_completed"}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("new executive brief", encoding="utf-8")
    return ExecutiveBriefStageResult(
        executive_brief_status="completed",
        analytics_input_path=str(analytics_input_path),
        ai_input_path=str(ai_input_path),
        external_input_path=str(external_input_path),
        content_feed_input_path=str(content_feed_input_path),
        output_path=str(output),
        report_date="2026-07-31",
        generation_mode="local_rules",
    )
