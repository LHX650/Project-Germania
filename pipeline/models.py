"""Auditable status models for the automated intelligence pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PipelineTimestamps:
    """UTC timestamps for every orchestration boundary."""

    pipeline_started_at: str | None = None
    archive_completed_at: str | None = None
    collection_started_at: str | None = None
    collection_completed_at: str | None = None
    analytics_started_at: str | None = None
    analytics_completed_at: str | None = None
    ai_started_at: str | None = None
    ai_completed_at: str | None = None
    external_intelligence_started_at: str | None = None
    external_intelligence_completed_at: str | None = None
    content_feed_started_at: str | None = None
    content_feed_completed_at: str | None = None
    strategic_started_at: str | None = None
    strategic_completed_at: str | None = None
    pipeline_completed_at: str | None = None


@dataclass(frozen=True)
class PipelineStatus:
    """Complete JSON-serializable state for one intelligence run."""

    pipeline_id: str
    pipeline_status: str
    run_id: str | None
    collection_exit_code: int | None
    collection_status: str
    analytics_status: str
    ai_status: str
    external_intelligence_status: str
    content_feed_status: str
    strategic_status: str
    timestamps: PipelineTimestamps
    report_paths: dict[str, str]
    archive_path: str | None
    errors: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation with required top-level statuses."""

        return asdict(self)


@dataclass(frozen=True)
class PipelineRunResult:
    """Pipeline status plus preserved output from the unchanged daily monitor."""

    status: PipelineStatus
    collection_exit_code: int | None
    collection_stdout: str
    collection_stderr: str
