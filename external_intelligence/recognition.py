"""Deterministic brand and tracked-model recognition for news text."""

from __future__ import annotations

import re

_BRAND_ALIASES = {
    "Volkswagen": ("volkswagen", "vw"),
    "BMW": ("bmw", "bmw group"),
    "Mercedes-Benz": ("mercedes-benz", "mercedes benz", "mercedes"),
    "Audi": ("audi",),
    "Tesla": ("tesla",),
    "BYD": ("byd", "build your dreams"),
}


def recognize_entities(
    text: str,
    *,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    source_brand: str | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Recognize only configured brands and tracked vehicle names."""

    normalized = _normalize(text)
    brands: set[str] = set()
    candidates = set(tracked_brands)
    if source_brand:
        candidates.add(source_brand)
        brands.add(source_brand)
    for brand in candidates:
        aliases = _BRAND_ALIASES.get(brand, (brand,))
        if any(_contains(normalized, alias) for alias in aliases):
            brands.add(brand)

    vehicles = set()
    for vehicle in tracked_vehicles:
        full_name = _normalize(vehicle)
        model_name = full_name
        for brand in sorted(candidates, key=len, reverse=True):
            brand_name = _normalize(brand)
            if full_name.startswith(f"{brand_name} "):
                model_name = full_name[len(brand_name) + 1 :]
                break
        if _contains(normalized, full_name) or (
            len(model_name) >= 3 and _contains(normalized, model_name)
        ):
            vehicles.add(vehicle)
    return tuple(sorted(brands)), tuple(sorted(vehicles))


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def _contains(text: str, value: str) -> bool:
    token = _normalize(value)
    return bool(token) and f" {token} " in f" {text} "
