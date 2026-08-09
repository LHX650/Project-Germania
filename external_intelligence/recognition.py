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
    "MG": ("mg", "mg motor"),
    "NIO": ("nio",),
    "XPENG": ("xpeng", "x peng", "xiaopeng"),
    "Škoda": ("škoda", "skoda", "skoda auto"),
}

_VEHICLE_ALIASES = {
    "Volkswagen Golf": ("volkswagen golf", "vw golf", "golf"),
    "Volkswagen Tiguan": ("volkswagen tiguan", "vw tiguan", "tiguan"),
    "Volkswagen ID.3": ("volkswagen id.3", "vw id.3", "id.3", "id3"),
    "Volkswagen ID.4": ("volkswagen id.4", "vw id.4", "id.4", "id4"),
    "BMW 3 Series": ("bmw 3 series", "3 series", "3-series", "3er", "3er reihe"),
    "BMW X3": ("bmw x3", "x3"),
    "Mercedes-Benz C-Class": (
        "mercedes-benz c-class",
        "mercedes c-class",
        "c-class",
        "c class",
        "c-klasse",
        "c klasse",
    ),
    "Mercedes-Benz GLC": ("mercedes-benz glc", "mercedes glc", "glc"),
    "Audi A3": ("audi a3", "a3"),
    "Audi Q4 e-tron": ("audi q4 e-tron", "q4 e-tron", "q4 etron"),
    "Tesla Model 3": ("tesla model 3", "model 3"),
    "Tesla Model Y": ("tesla model y", "model y"),
    "BYD Seal": ("byd seal", "seal"),
    "BYD Atto 3": ("byd atto 3", "atto 3", "yuan plus"),
    "BYD Seal U": ("byd seal u", "seal u", "seal u dm-i", "seal-u"),
    "MG MG4": ("mg mg4", "mg4 electric", "mg4", "mg 4"),
    "MG ZS EV": ("mg zs ev", "zs ev", "mg zs electric"),
    "Škoda Enyaq": ("škoda enyaq", "skoda enyaq", "enyaq"),
    "NIO EL6": ("nio el6", "el6"),
    "XPENG G6": ("xpeng g6", "x peng g6", "g6"),
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

    matched: list[tuple[str, str, str]] = []
    for vehicle in tracked_vehicles:
        full_name = _normalize(vehicle)
        model_name = full_name
        vehicle_brand = ""
        canonical_brand = ""
        for brand in sorted(candidates, key=len, reverse=True):
            brand_name = _normalize(brand)
            if full_name.startswith(f"{brand_name} "):
                model_name = full_name[len(brand_name) + 1 :]
                vehicle_brand = brand_name
                canonical_brand = brand
                break
        aliases = _VEHICLE_ALIASES.get(vehicle, (full_name, model_name))
        brand_context = canonical_brand in brands or source_brand == canonical_brand
        if any(
            _contains(normalized, alias)
            and (len(_normalize(alias)) >= 3 or brand_context)
            for alias in aliases
        ):
            matched.append((vehicle, vehicle_brand, model_name))

    vehicles: set[str] = set()
    longer_models: list[tuple[str, str]] = []
    for vehicle, vehicle_brand, model_name in sorted(
        matched,
        key=lambda value: len(value[2]),
        reverse=True,
    ):
        competing = tuple(
            longer
            for brand_name, longer in longer_models
            if brand_name == vehicle_brand
            and model_name != longer
            and _contains(longer, model_name)
        )
        remaining_text = normalized
        for longer in competing:
            remaining_text = re.sub(
                rf"(?<!\w){re.escape(longer)}(?!\w)",
                " ",
                remaining_text,
            )
        if not competing or _contains(remaining_text, model_name):
            vehicles.add(vehicle)
        longer_models.append((vehicle_brand, model_name))
    return tuple(sorted(brands)), tuple(sorted(vehicles))


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def _contains(text: str, value: str) -> bool:
    token = _normalize(value)
    return bool(token) and f" {token} " in f" {text} "
