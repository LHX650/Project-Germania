"""Tests for dynamic, read-only AI Markdown report access."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.ai_report import (
    AIReportError,
    clear_ai_report_cache,
    load_daily_ai_market_report,
)


def test_loads_dynamic_ai_report_sections_and_metadata(tmp_path: Path) -> None:
    report_path = tmp_path / "daily_ai_market_report.md"
    _write_report(report_path)

    report = load_daily_ai_market_report(report_path)

    assert report.title == "Dynamic German Market Report"
    assert report.generation_mode == "local_rules"
    assert report.provider_name is None
    assert report.analytics_date.isoformat() == "2026-07-31"
    assert report.generated_at_utc.tzinfo is not None
    assert "2,441 active listings" in report.market_overview_markdown
    assert "Dynamic Motors Alpha" in report.vehicle_opportunity_markdown
    assert "Opportunity" in report.market_opportunity_markdown
    assert "Measurement risk" in report.risk_markdown
    assert "Activity signal" not in report.risk_markdown
    assert report.source_path == report_path.resolve()


def test_cache_refreshes_after_incremental_report_update(tmp_path: Path) -> None:
    report_path = tmp_path / "daily_ai_market_report.md"
    _write_report(report_path, generation_mode="local_rules")
    first = load_daily_ai_market_report(report_path)

    _write_report(report_path, generation_mode="llm_grounded")
    second = load_daily_ai_market_report(report_path)

    assert first.generation_mode == "local_rules"
    assert second.generation_mode == "llm_grounded"
    assert first is not second


def test_missing_empty_and_incomplete_reports_fail_clearly(tmp_path: Path) -> None:
    with pytest.raises(AIReportError, match="was not found"):
        load_daily_ai_market_report(tmp_path / "missing.md")

    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(AIReportError, match="empty"):
        load_daily_ai_market_report(empty)

    incomplete = tmp_path / "incomplete.md"
    incomplete.write_text(
        "# Incomplete\n\n**Generation mode:** `local_rules`  \n"
        "**Analytics date:** 2026-07-31\n\n"
        "## Germany market overview\n\nOnly one section.\n",
        encoding="utf-8",
    )
    with pytest.raises(AIReportError, match="missing required sections"):
        load_daily_ai_market_report(incomplete)


def test_invalid_evidence_digest_is_rejected(tmp_path: Path) -> None:
    report_path = tmp_path / "invalid_digest.md"
    _write_report(report_path, evidence_sha256="not-a-digest")

    with pytest.raises(AIReportError, match="SHA-256 is invalid"):
        load_daily_ai_market_report(report_path)


@pytest.fixture(autouse=True)
def clear_cache_between_tests() -> None:
    clear_ai_report_cache()


def _write_report(
    path: Path,
    *,
    generation_mode: str = "local_rules",
    evidence_sha256: str = "a" * 64,
) -> None:
    path.write_text(
        f"""# Dynamic German Market Report

**Generation mode:** `{generation_mode}`
**LLM provider:** `none`
**Analytics evidence SHA-256:** `{evidence_sha256}`

**Analytics date:** 2026-07-31

## Germany market overview

The current report contains **2,441 active listings**.

## Brand competition analysis

Dynamic Motors leads the fixture.

## Vehicle opportunity analysis

- **Dynamic Motors Alpha** has the highest current project score.

## Price trend interpretation

Trend coverage is limited.

## Inventory change interpretation

Inventory changed during the reporting window.

## Risk and opportunity summary

- **Opportunity:** Dynamic Motors Alpha is the current research priority.
- **Activity signal:** New listings were present.
- **Trend-data risk:** Coverage is limited.
- **Measurement risk:** Asking prices are not transaction prices.
""",
        encoding="utf-8",
    )
