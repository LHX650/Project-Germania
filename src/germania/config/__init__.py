"""Configuration loading and normalization helpers."""

from __future__ import annotations

from germania.config.vehicle_normalization import (
    UNKNOWN,
    normalize_brand,
    normalize_model,
    normalize_powertrain,
)
from germania.config.vehicles import load_vehicle_config

__all__ = [
    "UNKNOWN",
    "load_vehicle_config",
    "normalize_brand",
    "normalize_model",
    "normalize_powertrain",
]
