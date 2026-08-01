from __future__ import annotations

from pathlib import Path

import pytest

from germania.config import (
    MarketplaceCollectionConfigError,
    load_collection_tasks,
)


def test_load_collection_tasks_filters_sorts_and_applies_default(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "marketplace_collection.yaml"
    config_path.write_text(
        """
defaults:
  max_pages: 4
tasks:
  - task_id: disabled_task
    source_id: autoscout24_de
    brand_name: Volkswagen
    model_name: Tiguan
    search_url: https://www.autoscout24.de/lst/volkswagen/tiguan
    enabled: false
    priority: 1
    notes: disabled
  - task_id: golf_task
    source_id: autoscout24_de
    brand_name: Volkswagen
    model_name: Golf
    search_url: https://www.autoscout24.de/lst/volkswagen/golf
    enabled: true
    priority: 20
    notes: uses default pages
  - task_id: model_y_task
    source_id: autoscout24_de
    brand_name: Tesla
    model_name: Model Y
    search_url: https://www.autoscout24.de/lst/tesla/model-y
    max_pages: 2
    enabled: true
    priority: 10
    notes: explicit pages
    cohort: core_b
    excluded_title_terms:
      - Model X
""".strip(),
        encoding="utf-8",
    )

    tasks = load_collection_tasks(config_path)

    assert [task.task_id for task in tasks] == ["model_y_task", "golf_task"]
    assert tasks[0].max_pages == 2
    assert tasks[0].cohort == "core_b"
    assert tasks[0].excluded_title_terms == ("Model X",)
    assert tasks[1].max_pages == 4
    assert tasks[1].cohort == "default"
    assert len(load_collection_tasks(config_path, enabled_only=False)) == 3


def test_load_collection_tasks_rejects_invalid_title_exclusions(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "marketplace_collection.yaml"
    config_path.write_text(
        """
tasks:
  - task_id: golf_task
    source_id: autoscout24_de
    brand_name: Volkswagen
    model_name: Golf
    search_url: https://www.autoscout24.de/lst/volkswagen/golf
    max_pages: 1
    enabled: true
    priority: 1
    notes: invalid exclusion
    excluded_title_terms:
      - " "
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        MarketplaceCollectionConfigError,
        match="excluded_title_terms contains empty text",
    ):
        load_collection_tasks(config_path)


def test_load_collection_tasks_resolves_vehicle_reference(
    tmp_path: Path,
) -> None:
    vehicle_config_path = tmp_path / "vehicles.yaml"
    vehicle_config_path.write_text(
        """
vehicles:
  - canonical_brand: Volkswagen
    canonical_model: ID.4
    chinese_brand: 大众
    chinese_model: ID.4
    manufacturer: Volkswagen AG
    vehicle_segment: compact_electric_suv
    body_type: suv
    powertrain: battery_electric
    country_of_origin: Germany
    priority_level: high
    active: true
    aliases:
      brand: [Volkswagen]
      model: [ID.4]
    search_keywords: [ID.4]
    exclude_keywords: [ID.5, ID5]
""".strip(),
        encoding="utf-8",
    )
    task_config_path = tmp_path / "marketplace_collection.yaml"
    task_config_path.write_text(
        """
tasks:
  - task_id: volkswagen_id_4
    source_id: autoscout24_de
    vehicle_ref:
      canonical_brand: Volkswagen
      canonical_model: ID.4
    search_url: https://www.autoscout24.de/lst/volkswagen/id4
    enabled: true
    priority: 1
    notes: configured vehicle reference
""".strip(),
        encoding="utf-8",
    )

    task = load_collection_tasks(
        task_config_path,
        vehicle_config_path=vehicle_config_path,
    )[0]

    assert task.brand_name == "Volkswagen"
    assert task.model_name == "ID.4"
    assert task.search_keywords == ("ID.4",)
    assert task.excluded_title_terms == ("ID.5", "ID5")


def test_default_collection_tasks_include_mg4_vehicle_reference() -> None:
    tasks = {task.task_id: task for task in load_collection_tasks()}

    mg4 = tasks["mg4"]

    assert mg4.brand_name == "MG"
    assert mg4.model_name == "MG4"
    assert mg4.search_keywords == ("MG4",)
    assert mg4.excluded_title_terms == ("MG HS",)
    assert "/lst/mg/mg4?" in mg4.search_url
    assert mg4.enabled is True


def test_default_collection_tasks_use_current_autoscout24_model_slugs() -> None:
    tasks = {task.task_id: task for task in load_collection_tasks()}

    mg_zs_ev = tasks["mg_zs_ev"]
    volkswagen_id_3 = tasks["volkswagen_id_3"]

    assert mg_zs_ev.brand_name == "MG"
    assert mg_zs_ev.model_name == "ZS EV"
    assert mg_zs_ev.search_keywords == ("ZS EV",)
    assert "/lst/mg/zs/ft_elektro?" in mg_zs_ev.search_url
    assert volkswagen_id_3.brand_name == "Volkswagen"
    assert volkswagen_id_3.model_name == "ID.3"
    assert volkswagen_id_3.search_keywords == ("ID.3",)
    assert "/lst/volkswagen/id-3?" in volkswagen_id_3.search_url


def test_default_collection_tasks_fit_configured_cohorts_within_page_budget() -> None:
    tasks = load_collection_tasks()
    cohort_pages: dict[str, int] = {}
    for task in tasks:
        cohort_pages[task.cohort] = cohort_pages.get(task.cohort, 0) + task.max_pages

    assert len(tasks) == 20
    assert cohort_pages == {"core_a": 41, "core_b": 43}
    assert all(page_count <= 50 for page_count in cohort_pages.values())


def test_load_collection_tasks_rejects_invalid_cohort(tmp_path: Path) -> None:
    config_path = tmp_path / "marketplace_collection.yaml"
    config_path.write_text(
        """
tasks:
  - task_id: golf_task
    source_id: autoscout24_de
    brand_name: Volkswagen
    model_name: Golf
    search_url: https://www.autoscout24.de/lst/volkswagen/golf
    max_pages: 1
    enabled: true
    priority: 1
    cohort: "Core A"
    notes: invalid cohort
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(MarketplaceCollectionConfigError, match="cohort"):
        load_collection_tasks(config_path)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("task_id: golf_task", "task_id must be unique"),
        ("search_url: http://example.com/listings", "search_url"),
    ],
)
def test_load_collection_tasks_rejects_duplicate_ids_and_invalid_urls(
    tmp_path: Path,
    replacement: str,
    message: str,
) -> None:
    second_task = """
  - task_id: second_task
    source_id: autoscout24_de
    brand_name: Tesla
    model_name: Model Y
    search_url: https://www.autoscout24.de/lst/tesla/model-y
    max_pages: 1
    enabled: true
    priority: 2
    notes: second
"""
    if replacement.startswith("task_id"):
        second_task = second_task.replace("task_id: second_task", replacement)
    else:
        second_task = second_task.replace(
            "search_url: https://www.autoscout24.de/lst/tesla/model-y",
            replacement,
        )

    config_path = tmp_path / "marketplace_collection.yaml"
    config_path.write_text(
        """
tasks:
  - task_id: golf_task
    source_id: autoscout24_de
    brand_name: Volkswagen
    model_name: Golf
    search_url: https://www.autoscout24.de/lst/volkswagen/golf
    max_pages: 1
    enabled: true
    priority: 1
    notes: first
""" + second_task,
        encoding="utf-8",
    )

    with pytest.raises(MarketplaceCollectionConfigError, match=message):
        load_collection_tasks(config_path)
