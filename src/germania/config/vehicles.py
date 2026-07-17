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


class VehicleConfigError(ValueError):
    """Raised when vehicle configuration is missing or invalid."""


def load_vehicle_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load and validate the project vehicle YAML configuration."""
    path = Path(config_path) if config_path is not None else DEFAULT_VEHICLE_CONFIG_PATH
    logger.debug("Loading vehicle configuration from %s", path)

    if not path.exists():
        raise VehicleConfigError(f"Vehicle configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

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

    for index, vehicle in enumerate(vehicles):
        _validate_vehicle_entry(vehicle, index, path)


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


def _is_string_list(values: object) -> bool:
    return isinstance(values, list) and all(isinstance(value, str) for value in values)
