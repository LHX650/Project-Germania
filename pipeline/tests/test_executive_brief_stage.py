"""Tests for the isolated Executive Brief orchestration stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.executive_brief import run_executive_brief_stage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / "demo"
PRODUCTION_INPUTS = (
    PROJECT_ROOT / "reports" / "daily_market_intelligence.json",
    PROJECT_ROOT / "reports" / "daily_ai_market_report.md",
    PROJECT_ROOT / "reports" / "external_intelligence.json",
    PROJECT_ROOT / "reports" / "external_intelligence" / "content_feed.json",
    PROJECT_ROOT / "database" / "project_germania_live.sqlite3",
)


def test_demo_stage_generates_atomic_grounded_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    output = tmp_path / "daily_executive_intelligence_brief.md"

    result = run_executive_brief_stage(
        analytics_status="completed",
        ai_status="completed",
        external_intelligence_status="completed",
        content_feed_status="completed",
        analytics_input_path=DEMO_ROOT / "daily_market_intelligence.json",
        ai_input_path=DEMO_ROOT / "daily_ai_market_report.md",
        external_input_path=DEMO_ROOT / "external_intelligence.json",
        content_feed_input_path=DEMO_ROOT / "content_feed.json",
        output_path=output,
    )

    assert result.executive_brief_status == "completed"
    assert result.report_date == "2026-07-31"
    assert result.generation_mode == "local_rules"
    markdown = output.read_text(encoding="utf-8")
    assert "# Germany Automotive Executive Brief" in markdown
    assert "## Internal Market Evidence" in markdown
    assert "## External Market Signals" in markdown
    assert not output.with_suffix(".md.tmp").exists()


def test_generation_failure_preserves_previous_valid_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    output = tmp_path / "daily_executive_intelligence_brief.md"
    output.write_text("previous valid brief", encoding="utf-8")

    result = run_executive_brief_stage(
        analytics_status="completed",
        ai_status="completed",
        external_intelligence_status="completed",
        content_feed_status="completed",
        analytics_input_path=DEMO_ROOT / "daily_market_intelligence.json",
        ai_input_path=tmp_path / "missing_ai_report.md",
        external_input_path=DEMO_ROOT / "external_intelligence.json",
        content_feed_input_path=DEMO_ROOT / "content_feed.json",
        output_path=output,
    )

    assert result.executive_brief_status == "failed"
    assert result.error_message is not None
    assert output.read_text(encoding="utf-8") == "previous valid brief"
    assert not output.with_suffix(".md.tmp").exists()


def test_unavailable_external_evidence_skips_without_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "daily_executive_intelligence_brief.md"
    output.write_text("previous valid brief", encoding="utf-8")

    result = run_executive_brief_stage(
        analytics_status="completed",
        ai_status="completed",
        external_intelligence_status="failed",
        content_feed_status="skipped",
        analytics_input_path=DEMO_ROOT / "daily_market_intelligence.json",
        ai_input_path=DEMO_ROOT / "daily_ai_market_report.md",
        external_input_path=DEMO_ROOT / "external_intelligence.json",
        content_feed_input_path=DEMO_ROOT / "content_feed.json",
        output_path=output,
    )

    assert result.executive_brief_status == "skipped"
    assert result.error_message is not None
    assert output.read_text(encoding="utf-8") == "previous valid brief"


@pytest.mark.skipif(
    not all(path.is_file() for path in PRODUCTION_INPUTS),
    reason="production read-only artifacts are not present",
)
def test_production_stage_reads_current_artifacts_without_database_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("AI_PROVIDER", "local")
    database = PRODUCTION_INPUTS[-1]
    before = database.stat()

    result = run_executive_brief_stage(
        analytics_status="completed",
        ai_status="completed",
        external_intelligence_status="partially_completed",
        content_feed_status="partially_completed",
        analytics_input_path=PRODUCTION_INPUTS[0],
        ai_input_path=PRODUCTION_INPUTS[1],
        external_input_path=PRODUCTION_INPUTS[2],
        content_feed_input_path=PRODUCTION_INPUTS[3],
        output_path=tmp_path / "daily_executive_intelligence_brief.md",
    )

    after = database.stat()
    analytics_date = json.loads(PRODUCTION_INPUTS[0].read_text(encoding="utf-8"))[
        "date"
    ]
    assert result.executive_brief_status == "completed"
    assert result.report_date == analytics_date
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
