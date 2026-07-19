"""Configuration-driven marketplace collection tasks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MARKETPLACE_COLLECTION_CONFIG_PATH = (
    PROJECT_ROOT / "config" / "marketplace_collection.yaml"
)
DEFAULT_MAX_PAGES = 3
_TASK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_AUTOSCOUT24_HOSTS = frozenset({"autoscout24.de", "www.autoscout24.de"})
_REQUIRED_TASK_FIELDS = frozenset(
    {
        "task_id",
        "source_id",
        "brand_name",
        "model_name",
        "search_url",
        "enabled",
        "priority",
        "notes",
    }
)


class MarketplaceCollectionConfigError(ValueError):
    """Raised when marketplace collection configuration is invalid."""


@dataclass(frozen=True)
class CollectionTask:
    """One validated, bounded marketplace collection task."""

    task_id: str
    source_id: str
    brand_name: str
    model_name: str
    search_url: str
    max_pages: int
    enabled: bool
    priority: int
    notes: str
    excluded_title_terms: tuple[str, ...] = ()


def load_collection_tasks(
    config_path: Path | str | None = None,
    *,
    enabled_only: bool = True,
) -> tuple[CollectionTask, ...]:
    """Load, validate, filter, and priority-sort collection tasks from YAML."""

    path = (
        Path(config_path)
        if config_path is not None
        else DEFAULT_MARKETPLACE_COLLECTION_CONFIG_PATH
    )
    logger.debug("Loading marketplace collection tasks from %s", path)
    if not path.exists():
        raise MarketplaceCollectionConfigError(
            f"Marketplace collection configuration file not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file)
    except yaml.YAMLError as exc:
        raise MarketplaceCollectionConfigError(
            f"Invalid marketplace collection YAML in {path}: {exc}"
        ) from exc

    tasks = _parse_collection_tasks(data, path)
    if enabled_only:
        tasks = [task for task in tasks if task.enabled]
    return tuple(sorted(tasks, key=lambda task: (task.priority, task.task_id)))


def _parse_collection_tasks(data: object, path: Path) -> list[CollectionTask]:
    if not isinstance(data, dict):
        raise MarketplaceCollectionConfigError(
            f"Marketplace collection configuration must be a mapping: {path}"
        )

    default_max_pages = _default_max_pages(data, path)
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise MarketplaceCollectionConfigError(
            f"Marketplace collection configuration requires a non-empty tasks list: "
            f"{path}"
        )

    tasks: list[CollectionTask] = []
    task_ids: set[str] = set()
    for index, raw_task in enumerate(raw_tasks):
        task = _parse_task(raw_task, index, default_max_pages)
        if task.task_id in task_ids:
            raise MarketplaceCollectionConfigError(
                f"Collection task_id must be unique: {task.task_id}"
            )
        task_ids.add(task.task_id)
        tasks.append(task)
    return tasks


def _default_max_pages(data: dict[str, Any], path: Path) -> int:
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise MarketplaceCollectionConfigError(
            f"Marketplace collection defaults must be a mapping: {path}"
        )
    value = defaults.get("max_pages", DEFAULT_MAX_PAGES)
    return _positive_int(value, "defaults.max_pages")


def _parse_task(
    raw_task: object,
    index: int,
    default_max_pages: int,
) -> CollectionTask:
    if not isinstance(raw_task, dict):
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} must be a mapping"
        )

    missing = _REQUIRED_TASK_FIELDS.difference(raw_task)
    if missing:
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} is missing required fields: "
            f"{', '.join(sorted(missing))}"
        )

    task_id = _required_text(raw_task["task_id"], f"task {index} task_id")
    if _TASK_ID_PATTERN.fullmatch(task_id) is None:
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} task_id must use lowercase letters, digits, "
            "hyphens, or underscores"
        )

    source_id = _required_text(raw_task["source_id"], f"task {index} source_id")
    brand_name = _required_text(raw_task["brand_name"], f"task {index} brand_name")
    model_name = _required_text(raw_task["model_name"], f"task {index} model_name")
    search_url = _required_text(raw_task["search_url"], f"task {index} search_url")
    _validate_search_url(search_url, index)

    enabled = raw_task["enabled"]
    if not isinstance(enabled, bool):
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} enabled must be boolean"
        )

    notes = raw_task["notes"]
    if not isinstance(notes, str):
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} notes must be text"
        )

    return CollectionTask(
        task_id=task_id,
        source_id=source_id,
        brand_name=brand_name,
        model_name=model_name,
        search_url=search_url,
        max_pages=_positive_int(
            raw_task.get("max_pages", default_max_pages),
            f"task {index} max_pages",
        ),
        enabled=enabled,
        priority=_non_negative_int(raw_task["priority"], f"task {index} priority"),
        notes=notes.strip(),
        excluded_title_terms=_excluded_title_terms(raw_task, index),
    )


def _excluded_title_terms(
    raw_task: dict[str, Any],
    index: int,
) -> tuple[str, ...]:
    values = raw_task.get("excluded_title_terms", [])
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} excluded_title_terms must be a string list"
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = " ".join(value.strip().split())
        if not term:
            raise MarketplaceCollectionConfigError(
                f"Collection task {index} excluded_title_terms contains empty text"
            )
        key = term.casefold()
        if key in seen:
            raise MarketplaceCollectionConfigError(
                f"Collection task {index} excluded_title_terms contains duplicate: "
                f"{term}"
            )
        seen.add(key)
        normalized.append(term)
    return tuple(normalized)


def _validate_search_url(search_url: str, index: int) -> None:
    parsed = urlparse(search_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _AUTOSCOUT24_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path.startswith("/lst/")
    ):
        raise MarketplaceCollectionConfigError(
            f"Collection task {index} search_url must be an HTTPS AutoScout24 "
            "Germany listing-search URL"
        )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceCollectionConfigError(f"{field} must be non-empty text")
    return " ".join(value.strip().split())


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MarketplaceCollectionConfigError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MarketplaceCollectionConfigError(
            f"{field} must be a non-negative integer"
        )
    return value
