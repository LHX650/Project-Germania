"""Data source YAML configuration loader."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"

REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "source_name",
        "source_type",
        "country_code",
        "base_url",
        "data_categories",
        "update_frequency",
        "authority_level",
        "active",
        "collection_method",
        "notes",
    }
)
ALLOWED_SOURCE_TYPES = frozenset(
    {
        "government",
        "industry_association",
        "central_bank",
        "manufacturer",
        "marketplace",
    }
)
ALLOWED_DATA_CATEGORIES = frozenset(
    {
        "registrations",
        "official_prices",
        "listings",
        "exchange_rates",
        "market_statistics",
        "vehicle_specifications",
    }
)
ALLOWED_UPDATE_FREQUENCIES = frozenset(
    {"daily", "weekly", "monthly", "quarterly", "irregular", "manual"}
)
ALLOWED_AUTHORITY_LEVELS = frozenset(
    {
        "primary_authoritative",
        "primary_commercial",
        "secondary_authoritative",
        "secondary_commercial",
    }
)
ALLOWED_COLLECTION_METHODS = frozenset(
    {"manual_download", "api", "html_parse", "browser_automation", "manual_entry"}
)

_SOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


class SourceConfigError(ValueError):
    """Raised when source configuration is missing or invalid."""


def load_source_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load and validate the project data source YAML configuration."""
    path = Path(config_path) if config_path is not None else DEFAULT_SOURCE_CONFIG_PATH
    logger.debug("Loading source configuration from %s", path)

    if not path.exists():
        raise _source_config_error(path, "<global>", "file", "file not found")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise _source_config_error(
            path,
            "<global>",
            "yaml",
            f"invalid YAML: {exc}",
        ) from exc

    _validate_source_config(data, path)
    return data


def _validate_source_config(data: object, path: Path) -> None:
    if not isinstance(data, dict):
        raise _source_config_error(
            path,
            "<global>",
            "top_level",
            "source configuration must be a mapping",
        )

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise _source_config_error(
            path,
            "<global>",
            "sources",
            "source configuration must contain a non-empty sources list",
        )

    seen_source_ids: set[str] = set()
    for index, source in enumerate(sources):
        source_id = _source_id_for_error(source, index)
        _validate_source_entry(source, source_id, path)

        if source_id in seen_source_ids:
            raise _source_config_error(
                path,
                source_id,
                "source_id",
                "duplicate source_id",
            )
        seen_source_ids.add(source_id)


def _validate_source_entry(source: object, source_id: str, path: Path) -> None:
    if not isinstance(source, dict):
        raise _source_config_error(
            path,
            source_id,
            "source",
            "source entry must be a mapping",
        )

    missing_fields = REQUIRED_SOURCE_FIELDS.difference(source)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise _source_config_error(
            path,
            source_id,
            "required_fields",
            f"missing required fields: {missing}",
        )

    _validate_source_id(source["source_id"], path)
    _validate_non_empty_string(source["source_name"], path, source_id, "source_name")
    _validate_enum(
        source["source_type"],
        ALLOWED_SOURCE_TYPES,
        path,
        source_id,
        "source_type",
    )
    _validate_country_code(source["country_code"], path, source_id)
    _validate_base_url(source["base_url"], path, source_id)
    _validate_data_categories(source["data_categories"], path, source_id)
    _validate_enum(
        source["update_frequency"],
        ALLOWED_UPDATE_FREQUENCIES,
        path,
        source_id,
        "update_frequency",
    )
    _validate_enum(
        source["authority_level"],
        ALLOWED_AUTHORITY_LEVELS,
        path,
        source_id,
        "authority_level",
    )
    if not isinstance(source["active"], bool):
        raise _source_config_error(
            path,
            source_id,
            "active",
            "active must be a boolean",
        )
    _validate_enum(
        source["collection_method"],
        ALLOWED_COLLECTION_METHODS,
        path,
        source_id,
        "collection_method",
    )
    _validate_non_empty_string(source["notes"], path, source_id, "notes")


def _validate_source_id(value: object, path: Path) -> None:
    source_id = value if isinstance(value, str) else "<invalid>"
    if not isinstance(value, str) or not _SOURCE_ID_PATTERN.fullmatch(value):
        raise _source_config_error(
            path,
            source_id,
            "source_id",
            "source_id must be unique snake_case text",
        )


def _validate_non_empty_string(
    value: object,
    path: Path,
    source_id: str,
    field: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _source_config_error(
            path,
            source_id,
            field,
            f"{field} must be a non-empty string",
        )


def _validate_enum(
    value: object,
    allowed_values: frozenset[str],
    path: Path,
    source_id: str,
    field: str,
) -> None:
    if not isinstance(value, str) or value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise _source_config_error(
            path,
            source_id,
            field,
            f"{field} must be one of: {allowed}",
        )


def _validate_country_code(value: object, path: Path, source_id: str) -> None:
    if not isinstance(value, str) or not _COUNTRY_CODE_PATTERN.fullmatch(value):
        raise _source_config_error(
            path,
            source_id,
            "country_code",
            "country_code must use two uppercase letters such as DE or EU",
        )


def _validate_base_url(value: object, path: Path, source_id: str) -> None:
    if value is None:
        return

    if not isinstance(value, str) or not value.strip():
        raise _source_config_error(
            path,
            source_id,
            "base_url",
            "base_url must be null or a non-empty HTTP(S) URL",
        )

    if not value.startswith(("https://", "http://")):
        raise _source_config_error(
            path,
            source_id,
            "base_url",
            "base_url must be null or a non-empty HTTP(S) URL",
        )


def _validate_data_categories(value: object, path: Path, source_id: str) -> None:
    if not isinstance(value, list) or not value:
        raise _source_config_error(
            path,
            source_id,
            "data_categories",
            "data_categories must be a non-empty list",
        )

    for category in value:
        if not isinstance(category, str) or category not in ALLOWED_DATA_CATEGORIES:
            allowed = ", ".join(sorted(ALLOWED_DATA_CATEGORIES))
            raise _source_config_error(
                path,
                source_id,
                "data_categories",
                f"data_categories entries must be one of: {allowed}",
            )


def _source_id_for_error(source: object, index: int) -> str:
    if isinstance(source, dict):
        source_id = source.get("source_id")
        if isinstance(source_id, str) and source_id:
            return source_id
    return f"<index:{index}>"


def _source_config_error(
    path: Path,
    source_id: str,
    field: str,
    reason: str,
) -> SourceConfigError:
    return SourceConfigError(
        f"path={path} | source_id={source_id} | field={field} | reason={reason}"
    )
