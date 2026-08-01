"""Collection-run persistence for governed AutoScout24 task batches."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.config.marketplace_collection import CollectionTask
from germania.db.models import CollectionBatch
from germania.db.repositories import BaseRepository, DataSourceRepository

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
CollectionBatchStatus = Literal[
    "completed",
    "partially_completed",
    "failed",
]


@dataclass(frozen=True)
class CollectionBatchOutcome:
    """Final task metrics persisted in one collection batch."""

    status: CollectionBatchStatus
    requested_pages: int
    succeeded_pages: int
    failed_pages: int
    parsed: int
    matched: int
    rejected: int
    low_confidence: int
    import_rejected: int
    observations_inserted: int
    error_message: str | None = None

    @property
    def page_success_rate(self) -> float:
        """Return successful requested pages as a value between zero and one."""

        if self.requested_pages == 0:
            return 0.0
        return self.succeeded_pages / self.requested_pages


def generate_collection_run_id(now: datetime | None = None) -> str:
    """Return a compact unique run ID suitable for collection batch keys."""

    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    return f"as24-{timestamp:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"


def validate_collection_run_id(run_id: str) -> str:
    """Validate and normalize a caller-provided collection run ID."""

    normalized = run_id.strip()
    if _RUN_ID_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "run_id must be 1-80 characters using letters, digits, '.', '_', "
            "':', or '-'"
        )
    return normalized


def create_task_collection_batch(
    session: Session,
    *,
    run_id: str,
    task: CollectionTask,
    raw_html_dir: Path,
    started_at: datetime | None = None,
) -> CollectionBatch:
    """Create a running collection batch for one configured task."""

    source = DataSourceRepository(session).get_by_source_id(task.source_id)
    if source is None:
        raise ValueError(
            f"Data source is not available for collection batch: {task.source_id}"
        )

    resolved_run_id = validate_collection_run_id(run_id)
    batch_id = f"{resolved_run_id}:{task.task_id}"
    if len(batch_id) > 120:
        raise ValueError("run_id and task_id produce a batch_id longer than 120")
    existing_batch_id = session.scalar(
        select(CollectionBatch.collection_batch_id).where(
            CollectionBatch.batch_id == batch_id
        )
    )
    if existing_batch_id is not None:
        raise ValueError(
            "collection batch already exists for "
            f"run_id={resolved_run_id} task_id={task.task_id}"
        )

    notes = _json_notes(
        {
            "run_id": resolved_run_id,
            "task_id": task.task_id,
            "cohort": task.cohort,
            "phase": "running",
        }
    )
    return BaseRepository(session, CollectionBatch).add(
        CollectionBatch(
            data_source_id=source.data_source_id,
            batch_id=batch_id,
            record_type="marketplace_listing",
            collection_method="browser_automation",
            collection_job_id=resolved_run_id,
            started_at=started_at or datetime.now(UTC),
            completed_at=None,
            status="running",
            record_count=None,
            success_count=None,
            failure_count=None,
            source_file_name=None,
            raw_file_path=str(raw_html_dir),
            raw_payload_reference=task.task_id,
            parser_version="autoscout24-v2",
            checksum=None,
            notes=notes,
        )
    )


def finalize_task_collection_batch(
    session: Session,
    batch: CollectionBatch,
    *,
    task: CollectionTask,
    outcome: CollectionBatchOutcome,
    completed_at: datetime | None = None,
) -> CollectionBatch:
    """Finalize a task batch with page, matching, and observation metrics."""

    notes = _json_notes(
        {
            "run_id": batch.collection_job_id,
            "task_id": task.task_id,
            "cohort": task.cohort,
            "phase": "finished",
            "requested_pages": outcome.requested_pages,
            "succeeded_pages": outcome.succeeded_pages,
            "failed_pages": outcome.failed_pages,
            "page_success_rate": round(outcome.page_success_rate, 6),
            "matched": outcome.matched,
            "rejected": outcome.rejected,
            "low_confidence": outcome.low_confidence,
            "import_rejected": outcome.import_rejected,
            "observations_inserted": outcome.observations_inserted,
            "error_message": outcome.error_message,
        }
    )
    return BaseRepository(session, CollectionBatch).update(
        batch,
        {
            "completed_at": completed_at or datetime.now(UTC),
            "status": outcome.status,
            "record_count": outcome.parsed,
            "success_count": outcome.matched,
            "failure_count": outcome.rejected + outcome.low_confidence,
            "notes": notes,
        },
    )


def _json_notes(values: dict[str, object]) -> str:
    return json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
