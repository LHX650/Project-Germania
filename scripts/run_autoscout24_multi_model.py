"""Run configuration-driven multi-model AutoScout24 collection."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24MultiModelCollectionPipeline,
)
from germania.config import CollectionTask, load_collection_tasks
from germania.db import create_database_engine, create_session_factory, session_scope


def main() -> int:
    """Collect configured AutoScout24 tasks and print JSON statistics."""

    arguments = _parse_arguments()
    tasks = _select_tasks(
        load_collection_tasks(arguments.config),
        arguments.task_id,
    )
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            result = AutoScout24MultiModelCollectionPipeline(
                AutoScout24Collector(),
                session,
            ).run(
                tasks,
                raw_html_dir=arguments.raw_html_dir,
                mode=arguments.mode,
            )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()
    return 0 if result.failed_tasks == 0 else 1


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect configured AutoScout24 Germany model batches.",
    )
    parser.add_argument("--mode", choices=("dry_run", "import"), required=True)
    parser.add_argument("--raw-html-dir", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--task-id", action="append")
    return parser.parse_args()


def _select_tasks(
    tasks: tuple[CollectionTask, ...],
    requested_task_ids: list[str] | None,
) -> tuple[CollectionTask, ...]:
    if not requested_task_ids:
        return tasks

    requested = set(requested_task_ids)
    selected = tuple(task for task in tasks if task.task_id in requested)
    missing = requested.difference(task.task_id for task in selected)
    if missing:
        raise ValueError(
            f"Unknown or disabled task_id values: {', '.join(sorted(missing))}"
        )
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
