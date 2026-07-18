"""Search URL builder for German AutoScout24 listing pages."""

from __future__ import annotations

from urllib.parse import quote, urlencode, urlparse

from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_BASE_URL,
    SearchConfig,
)

_ALLOWED_AUTOSCOUT24_HOSTS = frozenset({"autoscout24.de", "www.autoscout24.de"})


def build_search_url(
    search_config: SearchConfig,
    *,
    base_url: str = AUTOSCOUT24_DE_BASE_URL,
) -> str:
    """Build a deterministic German AutoScout24 search URL."""
    normalized_base_url = _normalize_autoscout24_de_base_url(base_url)
    path_parts = ["lst", _slugify_path_component(search_config.brand)]
    if search_config.model is not None:
        path_parts.append(_slugify_path_component(search_config.model))

    query = _build_query(search_config)
    return f"{normalized_base_url}/{'/'.join(path_parts)}?{urlencode(query)}"


def _build_query(search_config: SearchConfig) -> dict[str, str]:
    query = {
        "atype": "C",
        "cy": "D",
        "ustate": search_config.vehicle_state_query_value,
        "sort": search_config.sort,
        "desc": "0",
    }

    _add_optional(query, "zip", search_config.postal_code)
    _add_optional(query, "zipr", search_config.radius_km)
    _add_optional(query, "pricefrom", search_config.min_price_eur)
    _add_optional(query, "priceto", search_config.max_price_eur)
    _add_optional(query, "fregfrom", search_config.min_first_registration_year)
    _add_optional(query, "fregto", search_config.max_first_registration_year)
    _add_optional(query, "kmto", search_config.max_mileage_km)
    _add_optional(query, "fuel", search_config.fuel_type)
    _add_optional(query, "body", search_config.body_type)
    _add_optional(query, "seller", search_config.seller_type)
    if search_config.page > 1:
        query["page"] = str(search_config.page)

    return query


def _add_optional(
    query: dict[str, str],
    key: str,
    value: int | str | None,
) -> None:
    if value is not None:
        query[key] = str(value)


def _normalize_autoscout24_de_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.netloc not in _ALLOWED_AUTOSCOUT24_HOSTS:
        raise ValueError("Only https://www.autoscout24.de is supported")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _slugify_path_component(value: str) -> str:
    normalized = " ".join(value.strip().casefold().split()).replace("/", "-")
    return quote(normalized.replace(" ", "-"), safe="-")
