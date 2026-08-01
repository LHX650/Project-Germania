"""Tests for strict upstream AI report parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from strategic.ai_input import AIReportInputError, load_ai_report_evidence
from strategic.tests.test_pipeline import write_ai_report


def test_loads_ai_report_metadata_and_sections(tmp_path: Path) -> None:
    path = write_ai_report(tmp_path / "ai.md", evidence_sha256="a" * 64)

    report = load_ai_report_evidence(path)

    assert report.report_date.isoformat() == "2026-07-31"
    assert report.generation_mode == "local_rules"
    assert report.provider_name is None
    assert report.evidence_sha256 == "a" * 64
    assert "Germany market overview" in report.sections


def test_missing_and_invalid_ai_inputs_fail_clearly(tmp_path: Path) -> None:
    with pytest.raises(AIReportInputError, match="does not exist"):
        load_ai_report_evidence(tmp_path / "missing.md")

    invalid = tmp_path / "invalid.md"
    invalid.write_text("# Report\n\nNo metadata.", encoding="utf-8")
    with pytest.raises(AIReportInputError, match="metadata is missing"):
        load_ai_report_evidence(invalid)
