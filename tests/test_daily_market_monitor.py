from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from germania.collectors.autoscout24 import (
    AutoScout24MultiModelCollectionResult,
    AutoScout24TaskCollectionResult,
    VehicleMatchSummary,
)
from germania.config import CollectionTask
from scripts.daily_market_monitor import (
    DailyMarketMonitorSummary,
    _parse_arguments,
    _parse_date,
    database_url_from_path,
    generate_daily_run_id,
    main,
    reserve_run_output_directory,
    run_analytics_after_collection,
    run_daily_market_monitor,
    validate_daily_run_id,
)


def test_daily_runner_executes_both_cohorts_and_aggregates_results(
    tmp_path: Path,
) -> None:
    tasks = (
        _task("golf", "core_a"),
        _task("tiguan", "core_a"),
        _task("model_y", "core_b"),
    )
    calls: list[tuple[tuple[str, ...], Path, str]] = []
    times = iter(
        (
            datetime(2026, 7, 31, 1, tzinfo=UTC),
            datetime(2026, 7, 31, 2, tzinfo=UTC),
        )
    )

    def cohort_runner(
        cohort_tasks: tuple[CollectionTask, ...],
        raw_html_dir: Path,
        run_id: str,
    ) -> AutoScout24MultiModelCollectionResult:
        calls.append(
            (tuple(task.task_id for task in cohort_tasks), raw_html_dir, run_id)
        )
        if cohort_tasks[0].cohort == "core_a":
            return _result(
                cohort_tasks,
                run_id=run_id,
                inserted=3,
                observations=4,
                price_history=1,
            )
        return _result(
            cohort_tasks,
            run_id=run_id,
            inserted=2,
            observations=5,
            price_history=2,
        )

    summary = run_daily_market_monitor(
        tasks,
        raw_output_root=tmp_path / "raw",
        run_date=date(2026, 7, 31),
        run_id="daily-20260731-test",
        cohort_runner=cohort_runner,
        now_provider=lambda: next(times),
    )

    assert summary.status == "completed"
    assert summary.collection_status == "completed"
    assert summary.analytics_status == "not_started"
    assert summary.successful_cohorts == 2
    assert summary.failed_cohorts == 0
    assert summary.listings_inserted == 5
    assert summary.observations_inserted == 9
    assert summary.price_history_inserted == 3
    assert summary.started_at == "2026-07-31T01:00:00+00:00"
    assert summary.completed_at == "2026-07-31T02:00:00+00:00"
    assert [call[0] for call in calls] == [("golf", "tiguan"), ("model_y",)]
    assert all(call[2] == "daily-20260731-test" for call in calls)
    assert calls[0][1].is_dir()
    assert calls[1][1].is_dir()
    assert calls[0][1].parts[-3:] == (
        "2026-07-31",
        "daily-20260731-test",
        "core_a",
    )
    assert calls[1][1].name == "core_b"


def test_daily_runner_records_task_and_cohort_failures_then_continues(
    tmp_path: Path,
) -> None:
    tasks = (
        _task("golf", "core_a"),
        _task("tiguan", "core_a"),
        _task("model_y", "core_b"),
    )
    called_cohorts: list[str] = []

    def cohort_runner(
        cohort_tasks: tuple[CollectionTask, ...],
        raw_html_dir: Path,
        run_id: str,
    ) -> AutoScout24MultiModelCollectionResult:
        del raw_html_dir
        cohort = cohort_tasks[0].cohort
        called_cohorts.append(cohort)
        if cohort == "core_b":
            raise RuntimeError("simulated cohort failure")
        return _result(
            cohort_tasks,
            run_id=run_id,
            inserted=1,
            observations=1,
            price_history=1,
            failed_task_id="tiguan",
        )

    summary = run_daily_market_monitor(
        tasks,
        raw_output_root=tmp_path / "raw",
        run_date=date(2026, 7, 31),
        run_id="daily-20260731-partial",
        cohort_runner=cohort_runner,
    )

    assert called_cohorts == ["core_a", "core_b"]
    assert summary.status == "partially_completed"
    assert summary.collection_status == "partially_completed"
    assert summary.analytics_status == "not_started"
    assert summary.successful_cohorts == 0
    assert summary.failed_cohorts == 2
    assert summary.listings_inserted == 1
    assert summary.observations_inserted == 1
    assert summary.price_history_inserted == 1
    assert [cohort.status for cohort in summary.cohorts] == [
        "partially_completed",
        "failed",
    ]
    assert summary.cohorts[0].task_failures[0].task_id == "tiguan"
    assert summary.cohorts[1].requested_tasks == 1
    assert summary.cohorts[1].failed_tasks == 1
    assert summary.cohorts[1].task_failures[0].task_id == "model_y"
    assert "simulated cohort failure" in (summary.cohorts[1].error_message or "")


def test_daily_runner_rejects_reused_raw_run_directory(tmp_path: Path) -> None:
    run_root = reserve_run_output_directory(
        tmp_path,
        run_date=date(2026, 7, 31),
        run_id="daily-20260731-existing",
    )

    assert run_root.is_dir()
    with pytest.raises(FileExistsError, match="already exists"):
        reserve_run_output_directory(
            tmp_path,
            run_date=date(2026, 7, 31),
            run_id="daily-20260731-existing",
        )


def test_daily_runner_validates_date_run_id_and_database_path(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "germania.sqlite3"
    database_path.touch()

    generated = generate_daily_run_id(date(2026, 7, 31))
    assert generated.startswith("daily-20260731-")
    assert validate_daily_run_id("daily-20260731-manual") == ("daily-20260731-manual")
    assert database_url_from_path(database_path).endswith("/germania.sqlite3")
    assert _parse_date("2026-07-31") == date(2026, 7, 31)

    with pytest.raises(ValueError, match="Windows directory"):
        validate_daily_run_id("daily:invalid")
    with pytest.raises(ValueError, match="existing file"):
        database_url_from_path(tmp_path / "missing.sqlite3")
    with pytest.raises(argparse.ArgumentTypeError, match="YYYY-MM-DD"):
        _parse_date("31-07-2026")


def test_daily_runner_parses_scheduler_command_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "germania.sqlite3"
    raw_output_root = tmp_path / "raw"
    monkeypatch.setattr(
        "sys.argv",
        [
            "daily_market_monitor.py",
            "--database-path",
            str(database_path),
            "--date",
            "2026-07-31",
            "--run-id",
            "daily-20260731-scheduled",
            "--raw-output-root",
            str(raw_output_root),
        ],
    )

    arguments = _parse_arguments()

    assert arguments.database_path == database_path
    assert arguments.run_date == date(2026, 7, 31)
    assert arguments.run_id == "daily-20260731-scheduled"
    assert arguments.raw_output_root == raw_output_root
    assert arguments.analytics_output == Path("reports/daily_market_intelligence.json")


def test_daily_runner_main_returns_structured_setup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "daily_market_monitor.py",
            "--database-path",
            str(tmp_path / "missing.sqlite3"),
            "--date",
            "2026-07-31",
            "--run-id",
            "daily-20260731-failed-setup",
        ],
    )

    exit_code = main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["collection_status"] == "failed"
    assert payload["analytics_status"] == "skipped"
    assert payload["run_id"] == "daily-20260731-failed-setup"
    assert payload["successful_cohorts"] == 0
    assert payload["failed_cohorts"] == 2
    assert payload["observations_inserted"] == 0
    assert "database path must be an existing file" in payload["error_message"]


def test_daily_pipeline_generates_analytics_only_after_successful_collection(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary = _completed_daily_summary(tmp_path)
    report_path = tmp_path / "reports" / "daily_market_intelligence.json"

    def analytics_runner() -> Path:
        report_path.parent.mkdir()
        report_path.write_text('{"date":"2026-07-31"}', encoding="utf-8")
        return report_path

    with caplog.at_level(logging.INFO):
        result = run_analytics_after_collection(
            summary,
            analytics_runner=analytics_runner,
        )

    assert result.run_id == "daily-20260731-analytics"
    assert result.status == "completed"
    assert result.collection_status == "completed"
    assert result.analytics_status == "completed"
    assert result.analytics_report_path == str(report_path.resolve())
    assert report_path.is_file()
    assert "collection_status=completed" in caplog.text
    assert "analytics_status=completed" in caplog.text


def test_daily_pipeline_skips_analytics_when_collection_is_not_complete(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    completed = _completed_daily_summary(tmp_path)
    summary = replace(
        completed,
        status="partially_completed",
        collection_status="partially_completed",
    )
    report_path = tmp_path / "daily_market_intelligence.json"
    report_path.write_text("previous valid report", encoding="utf-8")

    def analytics_runner() -> Path:
        raise AssertionError("analytics must not run after failed collection")

    with caplog.at_level(logging.WARNING):
        result = run_analytics_after_collection(
            summary,
            analytics_runner=analytics_runner,
        )

    assert result.status == "partially_completed"
    assert result.collection_status == "partially_completed"
    assert result.analytics_status == "skipped"
    assert report_path.read_text(encoding="utf-8") == "previous valid report"
    assert "analytics_status=skipped" in caplog.text


def test_analytics_failure_does_not_change_successful_collection_result(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    summary = _completed_daily_summary(tmp_path)

    def analytics_runner() -> Path:
        raise RuntimeError("simulated analytics failure")

    with caplog.at_level(logging.ERROR):
        result = run_analytics_after_collection(
            summary,
            analytics_runner=analytics_runner,
        )

    assert result.status == "completed"
    assert result.collection_status == "completed"
    assert result.listings_inserted == summary.listings_inserted
    assert result.observations_inserted == summary.observations_inserted
    assert result.analytics_status == "failed"
    assert "simulated analytics failure" in (result.analytics_error_message or "")
    assert result.analytics_report_path is None
    assert "analytics_status=failed" in caplog.text


def test_main_runs_phase_5a_analytics_after_completed_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "germania.sqlite3"
    database_path.touch()
    report_path = tmp_path / "reports" / "daily_market_intelligence.json"
    summary = _completed_daily_summary(tmp_path)
    calls: dict[str, object] = {}

    class FakeEngine:
        disposed = False

        def dispose(self) -> None:
            self.disposed = True

    class FakeSession:
        def __enter__(self) -> FakeSession:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    engine = FakeEngine()
    monkeypatch.setattr(
        "sys.argv",
        [
            "daily_market_monitor.py",
            "--database-path",
            str(database_path),
            "--date",
            "2026-07-31",
            "--run-id",
            summary.run_id,
            "--raw-output-root",
            str(tmp_path / "main-raw"),
            "--analytics-output",
            str(report_path),
        ],
    )
    monkeypatch.setattr(
        "scripts.daily_market_monitor.load_collection_tasks", lambda config: ()
    )
    monkeypatch.setattr(
        "scripts.daily_market_monitor.create_database_engine", lambda url: engine
    )
    monkeypatch.setattr(
        "scripts.daily_market_monitor.create_session_factory",
        lambda selected_engine: FakeSession,
    )
    monkeypatch.setattr(
        "scripts.daily_market_monitor.run_daily_market_monitor",
        lambda *args, **kwargs: summary,
    )

    def build_report(session: object, *, report_date: date) -> object:
        calls["session"] = session
        calls["report_date"] = report_date
        return object()

    def write_report(report: object, output_path: Path) -> Path:
        calls["report"] = report
        calls["output_path"] = output_path
        output_path.parent.mkdir()
        output_path.write_text("{}", encoding="utf-8")
        return output_path

    monkeypatch.setattr(
        "scripts.daily_market_monitor.build_daily_market_intelligence",
        build_report,
    )
    monkeypatch.setattr(
        "scripts.daily_market_monitor.write_daily_market_intelligence",
        write_report,
    )

    exit_code = main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["run_id"] == summary.run_id
    assert payload["collection_status"] == "completed"
    assert payload["analytics_status"] == "completed"
    assert payload["analytics_report_path"] == str(report_path.resolve())
    assert calls["report_date"] == date(2026, 7, 31)
    assert calls["output_path"] == report_path
    assert engine.disposed is True


def _completed_daily_summary(tmp_path: Path) -> DailyMarketMonitorSummary:
    tasks = (_task("golf", "core_a"), _task("model_y", "core_b"))

    def cohort_runner(
        cohort_tasks: tuple[CollectionTask, ...],
        raw_html_dir: Path,
        run_id: str,
    ) -> AutoScout24MultiModelCollectionResult:
        del raw_html_dir
        return _result(
            cohort_tasks,
            run_id=run_id,
            inserted=1,
            observations=1,
            price_history=1,
        )

    return run_daily_market_monitor(
        tasks,
        raw_output_root=tmp_path / "raw",
        run_date=date(2026, 7, 31),
        run_id="daily-20260731-analytics",
        cohort_runner=cohort_runner,
    )


def _task(task_id: str, cohort: str) -> CollectionTask:
    return CollectionTask(
        task_id=task_id,
        source_id="autoscout24_de",
        brand_name="Volkswagen",
        model_name="Golf",
        search_url="https://www.autoscout24.de/lst/volkswagen/golf",
        max_pages=1,
        enabled=True,
        priority=1,
        notes="daily runner test",
        cohort=cohort,
    )


def _result(
    tasks: tuple[CollectionTask, ...],
    *,
    run_id: str,
    inserted: int,
    observations: int,
    price_history: int,
    failed_task_id: str | None = None,
) -> AutoScout24MultiModelCollectionResult:
    task_results = tuple(
        _task_result(
            task,
            inserted=inserted if index == 0 else 0,
            observations=observations if index == 0 else 0,
            price_history=price_history if index == 0 else 0,
            failed=task.task_id == failed_task_id,
        )
        for index, task in enumerate(tasks)
    )
    succeeded_tasks = sum(task.succeeded for task in task_results)
    failed_tasks = len(task_results) - succeeded_tasks
    return AutoScout24MultiModelCollectionResult(
        mode="import",
        run_id=run_id,
        requested_tasks=len(task_results),
        succeeded_tasks=succeeded_tasks,
        failed_tasks=failed_tasks,
        requested_pages=len(task_results),
        succeeded_pages=succeeded_tasks,
        failed_pages=failed_tasks,
        page_success_rate=succeeded_tasks / len(task_results),
        parsed=succeeded_tasks,
        matching=VehicleMatchSummary(matched=succeeded_tasks),
        inserted=inserted,
        updated=0,
        skipped=0,
        rejected=failed_tasks,
        price_history_inserted=price_history,
        observations_inserted=observations,
        tasks=task_results,
    )


def _task_result(
    task: CollectionTask,
    *,
    inserted: int,
    observations: int,
    price_history: int,
    failed: bool,
) -> AutoScout24TaskCollectionResult:
    return AutoScout24TaskCollectionResult(
        task_id=task.task_id,
        cohort=task.cohort,
        brand_name=task.brand_name,
        model_name=task.model_name,
        collection_batch_id=1,
        requested_pages=1,
        succeeded_pages=0 if failed else 1,
        failed_pages=1 if failed else 0,
        page_success_rate=0.0 if failed else 1.0,
        parsed=0 if failed else 1,
        matching=(
            VehicleMatchSummary(rejected=1)
            if failed
            else VehicleMatchSummary(matched=1)
        ),
        inserted=inserted,
        updated=0,
        skipped=0,
        rejected=1 if failed else 0,
        price_history_inserted=price_history,
        observations_inserted=observations,
        error_message="simulated task failure" if failed else None,
    )
