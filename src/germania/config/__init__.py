"""Configuration loading and normalization helpers."""

from __future__ import annotations

from germania.config.marketplace_collection import (
    CollectionTask,
    MarketplaceCollectionConfigError,
    load_collection_tasks,
)
from germania.config.playwright import load_playwright_config
from germania.config.sources import load_source_config
from germania.config.vehicle_normalization import (
    UNKNOWN,
    normalize_brand,
    normalize_model,
    normalize_powertrain,
)
from germania.config.vehicles import load_vehicle_config

__all__ = [
    "CollectionTask",
    "MarketplaceCollectionConfigError",
    "UNKNOWN",
    "load_playwright_config",
    "load_collection_tasks",
    "load_source_config",
    "load_vehicle_config",
    "normalize_brand",
    "normalize_model",
    "normalize_powertrain",
]
