from __future__ import annotations

import pytest

from germania.config import CollectionTask
from scripts.run_autoscout24_multi_model import _select_tasks


def test_select_tasks_supports_cohort_and_task_filters() -> None:
    tasks = (
        _task("golf", "core_a"),
        _task("tiguan", "core_a"),
        _task("model_y", "core_b"),
    )

    assert [task.task_id for task in _select_tasks(tasks, None, ["core_a"])] == [
        "golf",
        "tiguan",
    ]
    assert [
        task.task_id for task in _select_tasks(tasks, ["tiguan", "model_y"], ["core_a"])
    ] == ["tiguan"]


def test_select_tasks_rejects_unknown_cohort() -> None:
    with pytest.raises(ValueError, match="Unknown cohort"):
        _select_tasks((_task("golf", "core_a"),), None, ["missing"])


def _task(task_id: str, cohort: str) -> CollectionTask:
    return CollectionTask(
        task_id=task_id,
        source_id="autoscout24_de",
        brand_name="Volkswagen",
        model_name="Golf",
        search_url="https://www.autoscout24.de/lst/volkswagen/golf",
        max_pages=1,
        enabled=True,
        priority=1,
        notes="CLI cohort test",
        cohort=cohort,
    )
