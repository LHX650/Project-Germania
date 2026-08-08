"""Tests for modification-aware pipeline status loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from services.pipeline_status import (
    PipelineStatusError,
    clear_pipeline_status_cache,
    load_pipeline_status,
)


def test_loads_all_pipeline_stages_and_errors(tmp_path: Path) -> None:
    path = tmp_path / "pipeline_status.json"
    _write_status(path, strategic_status="completed")

    status = load_pipeline_status(path)

    assert status.pipeline_id == "pipeline-fixture"
    assert status.run_id == "daily-fixture"
    assert status.stages["collection"] == "completed"
    assert status.stages["external_intelligence"] == "partially_completed"
    assert status.stages["executive_brief"] == "completed"
    assert status.stages["strategic"] == "completed"
    assert status.errors == {"external_intelligence": "one source failed"}
    assert status.latest_timestamp is not None


def test_cache_refreshes_and_invalid_input_fails(tmp_path: Path) -> None:
    path = tmp_path / "pipeline_status.json"
    _write_status(path, strategic_status="completed")
    first = load_pipeline_status(path)

    _write_status(path, strategic_status="failed")
    second = load_pipeline_status(path)

    assert first.stages["strategic"] == "completed"
    assert second.stages["strategic"] == "failed"
    assert first is not second

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(PipelineStatusError, match="timestamps"):
        load_pipeline_status(invalid)


def test_pre_phase_18d_status_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "pipeline_status.json"
    _write_status(path, strategic_status="completed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["executive_brief_status"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    status = load_pipeline_status(path)

    assert status.stages["executive_brief"] == "not_available"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    clear_pipeline_status_cache()


def _write_status(path: Path, *, strategic_status: str) -> None:
    payload = {
        "pipeline_id": "pipeline-fixture",
        "pipeline_status": "partially_completed",
        "run_id": "daily-fixture",
        "collection_status": "completed",
        "analytics_status": "completed",
        "ai_status": "completed",
        "external_intelligence_status": "partially_completed",
        "content_feed_status": "completed",
        "executive_brief_status": "completed",
        "strategic_status": strategic_status,
        "timestamps": {
            "pipeline_started_at": "2026-08-01T00:00:00+00:00",
            "pipeline_completed_at": "2026-08-01T00:05:00+00:00",
        },
        "errors": {"external_intelligence": "one source failed"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
