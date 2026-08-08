"""Tests for atomic status persistence."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.models import PipelineStatus, PipelineTimestamps
from pipeline.storage import write_pipeline_status


def test_pipeline_status_is_atomic_and_has_required_fields(tmp_path: Path) -> None:
    output = tmp_path / "pipeline_status.json"
    status = PipelineStatus(
        pipeline_id="pipeline-test",
        pipeline_status="completed",
        run_id="daily-test",
        collection_exit_code=0,
        collection_status="completed",
        analytics_status="completed",
        ai_status="completed",
        external_intelligence_status="completed",
        content_feed_status="completed",
        executive_brief_status="completed",
        executive_brief_error_message=None,
        strategic_status="completed",
        timestamps=PipelineTimestamps(
            pipeline_started_at="2026-07-31T18:00:00+00:00",
            executive_brief_started_at="2026-07-31T18:00:30+00:00",
            executive_brief_completed_at="2026-07-31T18:00:40+00:00",
            pipeline_completed_at="2026-07-31T18:01:00+00:00",
        ),
        report_paths={},
        archive_path=None,
        errors={},
    )

    written = write_pipeline_status(status, output)

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["collection_status"] == "completed"
    assert payload["analytics_status"] == "completed"
    assert payload["ai_status"] == "completed"
    assert payload["external_intelligence_status"] == "completed"
    assert payload["content_feed_status"] == "completed"
    assert payload["executive_brief_status"] == "completed"
    assert payload["executive_brief_error_message"] is None
    assert payload["strategic_status"] == "completed"
    assert "timestamps" in payload
    assert payload["timestamps"]["executive_brief_started_at"] is not None
    assert payload["timestamps"]["executive_brief_completed_at"] is not None
    assert not output.with_suffix(".json.tmp").exists()
