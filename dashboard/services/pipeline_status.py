"""Validated, modification-aware access to the read-only pipeline status artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_PIPELINE_STATUS = Path("reports/pipeline_status.json")
PIPELINE_STAGES: tuple[str, ...] = (
    "collection",
    "analytics",
    "ai",
    "external_intelligence",
    "content_feed",
    "strategic",
)


class PipelineStatusError(RuntimeError):
    """Raised when the pipeline status artifact is missing or invalid."""


@dataclass(frozen=True)
class PipelineStatus:
    """Read-only status for the latest intelligence pipeline execution."""

    pipeline_id: str
    run_id: str | None
    overall_status: str
    stages: dict[str, str]
    timestamps: dict[str, datetime]
    errors: dict[str, str]
    source_path: Path

    @property
    def latest_timestamp(self) -> datetime | None:
        """Return the most recent validated timestamp in the artifact."""

        return max(self.timestamps.values(), default=None)


def load_pipeline_status(path: str | Path | None = None) -> PipelineStatus:
    """Load pipeline status and refresh the bounded cache after file changes."""

    resolved = _resolve(path)
    if not resolved.is_file():
        raise PipelineStatusError(
            "Pipeline status was not found at reports/pipeline_status.json."
        )
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise PipelineStatusError("Unable to inspect pipeline status.") from exc
    return _load_cached(str(resolved), stat.st_mtime_ns, stat.st_size)


def clear_pipeline_status_cache() -> None:
    """Clear the bounded file cache for tests and operations."""

    _load_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_cached(path_text: str, modified_at_ns: int, size: int) -> PipelineStatus:
    del modified_at_ns, size
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineStatusError(
            "Pipeline status is unreadable or is not valid UTF-8 JSON."
        ) from exc
    return _parse(payload, path)


def _parse(payload: object, source_path: Path) -> PipelineStatus:
    root = _mapping(payload, "pipeline status")
    timestamps = {
        _text(key, "timestamp name"): _timestamp(value, f"timestamps.{key}")
        for key, value in _mapping(root.get("timestamps"), "timestamps").items()
    }
    errors = {
        _text(key, "error stage"): _text(value, f"errors.{key}")
        for key, value in _mapping(root.get("errors", {}), "errors").items()
    }
    stages = {
        stage: _text(root.get(f"{stage}_status"), f"{stage}_status")
        for stage in PIPELINE_STAGES
    }
    run_id_value = root.get("run_id")
    return PipelineStatus(
        pipeline_id=_text(root.get("pipeline_id"), "pipeline_id"),
        run_id=None if run_id_value is None else _text(run_id_value, "run_id"),
        overall_status=_text(root.get("pipeline_status"), "pipeline_status"),
        stages=stages,
        timestamps=timestamps,
        errors=errors,
        source_path=source_path,
    )


def _resolve(path: str | Path | None) -> Path:
    candidate = Path(path).expanduser() if path is not None else DEFAULT_PIPELINE_STATUS
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[2] / candidate
    return candidate.resolve(strict=False)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineStatusError(f"{field} must be a JSON object.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineStatusError(f"{field} must be non-empty text.")
    return " ".join(value.split())


def _timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PipelineStatusError(f"{field} must use ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise PipelineStatusError(f"{field} must include a time zone.")
    return parsed.astimezone(UTC)
