"""Atomic pipeline-status storage and non-destructive report version archives."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from pipeline.models import PipelineStatus

logger = logging.getLogger(__name__)
_PIPELINE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


def write_pipeline_status(status: PipelineStatus, output_path: str | Path) -> Path:
    """Atomically persist the current pipeline state as UTF-8 JSON."""

    path = Path(output_path).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = json.dumps(status.to_dict(), ensure_ascii=False, indent=2)
    try:
        temporary_path.write_text(f"{payload}\n", encoding="utf-8")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    logger.info(
        "Pipeline status updated pipeline_id=%s pipeline_status=%s path=%s",
        status.pipeline_id,
        status.pipeline_status,
        path,
    )
    return path


def archive_existing_artifacts(
    *,
    pipeline_id: str,
    archive_root: str | Path,
    artifacts: dict[str, Path],
) -> Path:
    """Copy existing reports and status into an immutable per-run archive."""

    if _PIPELINE_ID_PATTERN.fullmatch(pipeline_id) is None:
        raise ValueError("pipeline_id is not safe for a version archive directory")
    root = Path(archive_root).expanduser().resolve(strict=False)
    archive_path = root / pipeline_id
    archive_path.mkdir(parents=True, exist_ok=False)
    copied: dict[str, str] = {}
    try:
        for artifact_name, source in artifacts.items():
            resolved_source = source.expanduser().resolve(strict=False)
            if not resolved_source.is_file():
                continue
            destination = archive_path / resolved_source.name
            shutil.copy2(resolved_source, destination)
            copied[artifact_name] = destination.name
        manifest = {
            "pipeline_id": pipeline_id,
            "artifacts": copied,
        }
        _write_json_atomically(manifest, archive_path / "archive_manifest.json")
    except Exception:
        logger.exception("Pipeline version archive failed path=%s", archive_path)
        raise
    logger.info(
        "Archived %s prior pipeline artifacts path=%s",
        len(copied),
        archive_path,
    )
    return archive_path


def _write_json_atomically(payload: object, path: Path) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
