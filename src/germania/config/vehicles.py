"""Vehicle YAML configuration loader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VEHICLE_CONFIG_PATH = PROJECT_ROOT / "config" / "vehicles.yaml"
REQUIRED_VEHICLE_FIELDS = frozenset(
    {
        "canonical_brand",
        "canonical_model",
        "chinese_brand",
        "chinese_model",
        "manufacturer",
        "vehicle_segment",
        "body_type",
        "powertrain",
        "country_of_origin",
        "priority_level",
        "active",
        "aliases",
    }
)
REQUIRED_STRING_FIELDS = REQUIRED_VEHICLE_FIELDS.difference({"active", "aliases"})
ALLOWED_PRIORITY_LEVELS = frozenset({"high", "medium", "low"})
ALLOWED_POWERTRAINS = frozenset(
    {
        "battery_electric",
        "hybrid",
        "internal_combustion",
        "multi_powertrain",
        "plug_in_hybrid",
        "unknown",
    }
)


class VehicleConfigError(ValueError):
    """Raised when vehicle configuration is missing or invalid."""


def load_vehicle_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load and validate the project vehicle YAML configuration."""
    path = Path(config_path) if config_path is not None else DEFAULT_VEHICLE_CONFIG_PATH
    logger.debug("Loading vehicle configuration from %s", path)

    if not path.exists():
        raise VehicleConfigError(f"Vehicle configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise VehicleConfigError(f"Invalid vehicle YAML in {path}: {exc}") from exc

    _validate_vehicle_config(data, path)
    return data


def _validate_vehicle_config(data: object, path: Path) -> None:
    if not isinstance(data, dict):
        raise VehicleConfigError(f"Vehicle configuration must be a mapping: {path}")

    vehicles = data.get("vehicles")
    if not isinstance(vehicles, list) or not vehicles:
        raise VehicleConfigError(
            f"Vehicle configuration must contain a non-empty vehicles list: {path}"
        )

    canonical_pairs: set[tuple[str, str]] = set()
    brand_aliases: dict[str, str] = {}
    model_aliases: dict[str, str] = {}

    for index, vehicle in enumerate(vehicles):
        _validate_vehicle_entry(vehicle, index, path)
        assert isinstance(vehicle, dict)

        canonical_brand = vehicle["canonical_brand"]
        canonical_model = vehicle["canonical_model"]
        assert isinstance(canonical_brand, str)
        assert isinstance(canonical_model, str)
        vehicle_label = f"{canonical_brand} {canonical_model}"

        canonical_pair = (canonical_brand, canonical_model)
        if canonical_pair in canonical_pairs:
            raise VehicleConfigError(
                f"Vehicle entry {index} duplicates canonical vehicle: {vehicle_label}"
            )
        canonical_pairs.add(canonical_pair)

        aliases = vehicle["aliases"]
        assert isinstance(aliases, dict)
        _track_aliases(
            aliases["brand"],
            brand_aliases,
            canonical_brand,
            index,
            "brand",
        )
        _track_aliases(
            aliases["model"],
            model_aliases,
            vehicle_label,
            index,
            "model",
        )


def _validate_vehicle_entry(vehicle: object, index: int, path: Path) -> None:
    if not isinstance(vehicle, dict):
        raise VehicleConfigError(
            f"Vehicle entry {index} must be a mapping in configuration: {path}"
        )

    missing_fields = REQUIRED_VEHICLE_FIELDS.difference(vehicle)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise VehicleConfigError(
            f"Vehicle entry {index} is missing required fields: {missing}"
        )

    for field in sorted(REQUIRED_STRING_FIELDS):
        if not isinstance(vehicle[field], str) or not vehicle[field].strip():
            raise VehicleConfigError(
                f"Vehicle entry {index} {field} must be a non-empty string"
            )

    if vehicle["priority_level"] not in ALLOWED_PRIORITY_LEVELS:
        allowed = ", ".join(sorted(ALLOWED_PRIORITY_LEVELS))
        raise VehicleConfigError(
            f"Vehicle entry {index} priority_level must be one of: {allowed}"
        )

    if vehicle["powertrain"] not in ALLOWED_POWERTRAINS:
        allowed = ", ".join(sorted(ALLOWED_POWERTRAINS))
        raise VehicleConfigError(
            f"Vehicle entry {index} powertrain must be one of: {allowed}"
        )

    if not isinstance(vehicle["active"], bool):
        raise VehicleConfigError(f"Vehicle entry {index} active must be boolean")

    aliases = vehicle["aliases"]
    if not isinstance(aliases, dict):
        raise VehicleConfigError(f"Vehicle entry {index} aliases must be a mapping")

    for alias_type in ("brand", "model"):
        values = aliases.get(alias_type)
        if not _is_string_list(values):
            raise VehicleConfigError(
                f"Vehicle entry {index} aliases.{alias_type} must be a string list"
            )
        _validate_alias_values(values, index, alias_type)


def _is_string_list(values: object) -> bool:
    return isinstance(values, list) and all(isinstance(value, str) for value in values)


def _validate_alias_values(values: list[str], index: int, alias_type: str) -> None:
    seen_aliases: set[str] = set()
    for value in values:
        alias_key = value.strip()
        if not alias_key:
            raise VehicleConfigError(
                f"Vehicle entry {index} aliases.{alias_type} contains an empty alias"
            )
        if alias_key in seen_aliases:
            raise VehicleConfigError(
                f"Vehicle entry {index} aliases.{alias_type} contains duplicate alias: "
                f"{value}"
            )
        seen_aliases.add(alias_key)


def _track_aliases(
    values: list[str],
    alias_index: dict[str, str],
    owner: str,
    vehicle_index: int,
    alias_type: str,
) -> None:
    for value in values:
        alias_key = _alias_key(value)
        previous_owner = alias_index.get(alias_key)
        if previous_owner is not None and previous_owner != owner:
            raise VehicleConfigError(
                f"Vehicle entry {vehicle_index} aliases.{alias_type} conflicts with "
                f"{previous_owner}: {value}"
            )
        alias_index[alias_key] = owner


def _alias_key(value: str) -> str:
    return " ".join(value.casefold().strip().split())
