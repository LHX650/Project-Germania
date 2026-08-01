"""Tests for report persistence and automatic three-stage gating."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ai.automated_pipeline import run_automated_intelligence_pipeline
from ai.pipeline import run_ai_report_stage
from ai.tests.test_models import analytics_payload, write_payload


def test_ai_stage_writes_report_after_completed_analytics(tmp_path: Path) -> None:
    source = write_payload(tmp_path / "daily.json")
    output = tmp_path / "report.md"

    result = run_ai_report_stage(
        analytics_status="completed",
        input_path=source,
        output_path=output,
    )

    assert result.ai_status == "completed"
    assert result.generation_mode == "local_rules"
    assert "Germany market overview" in output.read_text(encoding="utf-8")


def test_failed_analytics_skips_ai_and_preserves_old_report(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    output.write_text("old valid report", encoding="utf-8")

    result = run_ai_report_stage(
        analytics_status="failed",
        input_path=tmp_path / "missing.json",
        output_path=output,
    )

    assert result.ai_status == "skipped"
    assert output.read_text(encoding="utf-8") == "old valid report"


def test_invalid_input_fails_ai_and_preserves_old_report(tmp_path: Path) -> None:
    source = tmp_path / "daily.json"
    source.write_text("not json", encoding="utf-8")
    output = tmp_path / "report.md"
    output.write_text("old valid report", encoding="utf-8")

    result = run_ai_report_stage(
        analytics_status="completed",
        input_path=source,
        output_path=output,
    )

    assert result.ai_status == "failed"
    assert output.read_text(encoding="utf-8") == "old valid report"


def test_automated_wrapper_generates_only_after_completed_analytics(
    tmp_path: Path,
) -> None:
    source = write_payload(tmp_path / "daily.json", analytics_payload())
    output = tmp_path / "report.md"

    def fake_runner(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["daily_market_monitor.py"],
            returncode=0,
            stdout=json.dumps(
                {
                    "run_id": "run-123",
                    "collection_status": "completed",
                    "analytics_status": "completed",
                }
            ),
            stderr="existing log output",
        )

    result = run_automated_intelligence_pipeline(
        [],
        input_path=source,
        output_path=output,
        subprocess_runner=fake_runner,
    )

    assert result.collection_exit_code == 0
    assert result.run_id == "run-123"
    assert result.collection_stderr == "existing log output"
    assert result.ai_stage.ai_status == "completed"
    assert output.is_file()


def test_automated_wrapper_preserves_collection_failure_status(tmp_path: Path) -> None:
    output = tmp_path / "report.md"

    def fake_runner(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["daily_market_monitor.py"],
            returncode=7,
            stdout=json.dumps(
                {
                    "run_id": "run-failed",
                    "collection_status": "failed",
                    "analytics_status": "skipped",
                }
            ),
            stderr="collection failed",
        )

    result = run_automated_intelligence_pipeline(
        [],
        output_path=output,
        subprocess_runner=fake_runner,
    )

    assert result.collection_exit_code == 7
    assert result.collection_status == "failed"
    assert result.ai_stage.ai_status == "skipped"
    assert not output.exists()
