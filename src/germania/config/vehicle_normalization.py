"""Exact vehicle configuration normalization helpers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from germania.config.vehicles import load_vehicle_config

UNKNOWN = "unknown"

_NON_WORD_PATTERN = re.compile(r"[^\w]+", re.UNICODE)
_POWERTRAIN_ALIASES: dict[str, tuple[str, ...]] = {
    "battery_electric": (
        "battery electric",
        "battery_electric",
        "bev",
        "electric",
        "elektro",
        "ev",
    ),
    "internal_combustion": (
        "benzin",
        "combustion",
        "diesel",
        "gasoline",
        "ice",
        "internal combustion",
        "petrol",
        "verbrenner",
    ),
    "plug_in_hybrid": (
        "phev",
        "plug in hybrid",
        "plug-in hybrid",
        "plug_in_hybrid",
    ),
    "hybrid": ("full hybrid", "hev", "hybrid"),
    "multi_powertrain": ("mixed", "multi powertrain", "multi_powertrain"),
}


def normalize_brand(value: str | None) -> str:
    """Return the canonical brand for a known brand alias."""
    return _normalize_vehicle_field(value, "brand", "canonical_brand")


def normalize_model(value: str | None) -> str:
    """Return the canonical model for a known model alias."""
    return _normalize_vehicle_field(value, "model", "canonical_model")


def normalize_powertrain(value: str | None) -> str:
    """Return the canonical powertrain value for a known powertrain alias."""
    if value is None:
        return UNKNOWN

    key = _normalization_key(value)
    if not key:
        return UNKNOWN

    for canonical, aliases in _POWERTRAIN_ALIASES.items():
        candidates = (canonical, *aliases)
        if key in {_normalization_key(candidate) for candidate in candidates}:
            return canonical
    return UNKNOWN


def _normalize_vehicle_field(
    value: str | None,
    alias_type: str,
    canonical_field: str,
) -> str:
    if value is None:
        return UNKNOWN

    key = _normalization_key(value)
    if not key:
        return UNKNOWN

    config = load_vehicle_config()
    index = _build_alias_index(config, alias_type, canonical_field)
    return index.get(key, UNKNOWN)


def _build_alias_index(
    config: dict[str, Any],
    alias_type: str,
    canonical_field: str,
) -> dict[str, str]:
    index: dict[str, str] = {}
    collisions: set[str] = set()

    for vehicle in config["vehicles"]:
        canonical_value = vehicle[canonical_field]
        for alias in _iter_aliases(vehicle, alias_type, canonical_field):
            key = _normalization_key(alias)
            if not key:
                continue

            existing = index.get(key)
            if existing is not None and existing != canonical_value:
                collisions.add(key)
                continue

            index[key] = canonical_value

    for key in collisions:
        index.pop(key, None)
    return index


def _iter_aliases(
    vehicle: dict[str, Any],
    alias_type: str,
    canonical_field: str,
) -> Iterable[str]:
    yield vehicle[canonical_field]

    if alias_type == "brand":
        yield vehicle["chinese_brand"]
        yield vehicle["manufacturer"]
    elif alias_type == "model":
        yield vehicle["chinese_model"]

    aliases = vehicle.get("aliases", {})
    if isinstance(aliases, dict):
        yield from _string_values(aliases.get(alias_type, []))


def _string_values(values: object) -> Iterable[str]:
    if isinstance(values, str):
        yield values
        return

    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                yield value


def _normalization_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    compacted = _NON_WORD_PATTERN.sub("", without_marks.casefold())
    return compacted.replace("_", "")
