from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from germania.collectors.autoscout24.run_management import (
    CollectionBatchOutcome,
    create_task_collection_batch,
    finalize_task_collection_batch,
    generate_collection_run_id,
    validate_collection_run_id,
)
from germania.config import CollectionTask
from germania.db import (
    Base,
    CollectionBatch,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.repositories import BaseRepository
from germania.db.seed import seed_configuration


def test_collection_batch_records_run_task_timing_and_statistics(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    started_at = datetime(2026, 7, 31, 8, tzinfo=UTC)
    completed_at = datetime(2026, 7, 31, 8, 5, tzinfo=UTC)
    task = _task("volkswagen_golf")

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            batch = create_task_collection_batch(
                session,
                run_id="phase2-test",
                task=task,
                raw_html_dir=tmp_path / task.task_id,
                started_at=started_at,
            )
            finalize_task_collection_batch(
                session,
                batch,
                task=task,
                outcome=CollectionBatchOutcome(
                    status="partially_completed",
                    requested_pages=4,
                    succeeded_pages=3,
                    failed_pages=1,
                    parsed=12,
                    matched=9,
                    rejected=2,
                    low_confidence=1,
                    import_rejected=3,
                    observations_inserted=9,
                    error_message=None,
                ),
                completed_at=completed_at,
            )

            assert batch.collection_job_id == "phase2-test"
            assert batch.batch_id == "phase2-test:volkswagen_golf"
            assert batch.status == "partially_completed"
            assert batch.started_at == started_at
            assert batch.completed_at == completed_at
            assert batch.record_count == 12
            assert batch.success_count == 9
            assert batch.failure_count == 3
            notes = json.loads(batch.notes or "{}")
            assert notes["task_id"] == "volkswagen_golf"
            assert notes["cohort"] == "core_a"
            assert notes["page_success_rate"] == 0.75
            assert notes["observations_inserted"] == 9
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_duplicate_collection_batch_is_rejected_without_poisoning_session(
    tmp_path: Path,
) -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    task = _task("volkswagen_golf")

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            create_task_collection_batch(
                session,
                run_id="phase2-duplicate",
                task=task,
                raw_html_dir=tmp_path / "first",
            )

            with pytest.raises(ValueError, match="collection batch already exists"):
                create_task_collection_batch(
                    session,
                    run_id="phase2-duplicate",
                    task=task,
                    raw_html_dir=tmp_path / "second",
                )

            create_task_collection_batch(
                session,
                run_id="phase2-duplicate",
                task=_task("tesla_model_y"),
                raw_html_dir=tmp_path / "third",
            )
            assert BaseRepository(session, CollectionBatch).count() == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_collection_run_id_generation_and_validation() -> None:
    run_id = generate_collection_run_id(datetime(2026, 7, 31, 8, tzinfo=UTC))

    assert run_id.startswith("as24-20260731T080000Z-")
    assert validate_collection_run_id(f"  {run_id}  ") == run_id
    with pytest.raises(ValueError, match="run_id"):
        validate_collection_run_id("invalid run id")


def _task(task_id: str) -> CollectionTask:
    model = "Golf" if task_id == "volkswagen_golf" else "Model Y"
    return CollectionTask(
        task_id=task_id,
        source_id="autoscout24_de",
        brand_name="Volkswagen" if model == "Golf" else "Tesla",
        model_name=model,
        search_url=(
            "https://www.autoscout24.de/lst/volkswagen/golf"
            if model == "Golf"
            else "https://www.autoscout24.de/lst/tesla/model-y"
        ),
        max_pages=1,
        enabled=True,
        priority=1,
        notes="run management test",
        cohort="core_a",
    )
