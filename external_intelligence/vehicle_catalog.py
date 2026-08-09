"""Read-only catalog of vehicles enabled for marketplace monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MONITORED_VEHICLES_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "marketplace_collection.yaml"
)


@dataclass(frozen=True)
class MonitoredVehicle:
    """One enabled vehicle identity from the existing collection config."""

    brand: str
    model: str

    @property
    def display_name(self) -> str:
        """Return the canonical brand and model label used by intelligence data."""

        return f"{self.brand} {self.model}"


def load_monitored_vehicles(
    path: str | Path = DEFAULT_MONITORED_VEHICLES_CONFIG,
) -> tuple[MonitoredVehicle, ...]:
    """Load enabled monitoring tasks without changing collection configuration."""

    config_path = Path(path).expanduser().resolve(strict=True)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise ValueError("marketplace collection config must contain a task list")
    vehicles: list[MonitoredVehicle] = []
    for raw in payload["tasks"]:
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            continue
        brand, model = _task_identity(raw)
        vehicles.append(MonitoredVehicle(brand=brand, model=model))
    identities = [item.display_name.casefold() for item in vehicles]
    if len(identities) != len(set(identities)):
        raise ValueError(
            "enabled marketplace tasks contain duplicate vehicle identities"
        )
    if not vehicles:
        raise ValueError("marketplace collection config has no enabled vehicles")
    return tuple(vehicles)


def _task_identity(task: dict[str, Any]) -> tuple[str, str]:
    vehicle_ref = task.get("vehicle_ref")
    if isinstance(vehicle_ref, dict):
        brand = vehicle_ref.get("canonical_brand")
        model = vehicle_ref.get("canonical_model")
    else:
        brand = task.get("brand_name")
        model = task.get("model_name")
    brand_text = _text(brand, "brand")
    model_text = _text(model, "model")
    return brand_text, model_text


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"enabled marketplace task is missing {field}")
    return " ".join(value.split())
