"""Validated YAML configuration for external intelligence sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from external_intelligence.vehicle_catalog import load_monitored_vehicles

DEFAULT_CONFIG_PATH = Path("config/external_intelligence.yaml")


@dataclass(frozen=True)
class HTTPConfig:
    timeout_seconds: float
    max_bytes: int
    user_agent: str


@dataclass(frozen=True)
class KBAConfig:
    enabled: bool
    source_name: str
    source_page_url: str
    download_url_template: str
    period_lag_months: int
    ttl_seconds: int
    catalog_search_url_template: str | None = None


@dataclass(frozen=True)
class NewsSourceConfig:
    source_id: str
    source_name: str
    page_url: str
    feed_url: str | None
    country: str
    ttl_seconds: int
    brand: str | None = None


@dataclass(frozen=True)
class ExternalIntelligenceConfig:
    """Complete external-provider configuration."""

    cache_directory: Path
    output_path: Path
    http: HTTPConfig
    kba: KBAConfig
    news_sources: tuple[NewsSourceConfig, ...]
    brand_news_sources: tuple[NewsSourceConfig, ...]
    max_news_items_per_source: int


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> ExternalIntelligenceConfig:
    """Load and validate external-intelligence YAML configuration."""

    config_path = Path(path).expanduser().resolve(strict=True)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("external intelligence config must be a mapping")
    http = _mapping(payload, "http")
    cache = _mapping(payload, "cache")
    output = _mapping(payload, "output")
    kba = _mapping(payload, "kba")
    news = _mapping(payload, "news")
    brand_news = _mapping(payload, "brand_news")
    config = ExternalIntelligenceConfig(
        cache_directory=Path(_text(cache, "directory")),
        output_path=Path(_text(output, "path")),
        http=HTTPConfig(
            timeout_seconds=float(http.get("timeout_seconds", 20)),
            max_bytes=int(http.get("max_bytes", 25_000_000)),
            user_agent=_text(http, "user_agent"),
        ),
        kba=KBAConfig(
            enabled=bool(kba.get("enabled", True)),
            source_name=_text(kba, "source_name"),
            source_page_url=_https(kba, "source_page_url"),
            download_url_template=_https(kba, "download_url_template"),
            period_lag_months=int(kba.get("period_lag_months", 1)),
            ttl_seconds=_positive(kba, "ttl_seconds"),
            catalog_search_url_template=_optional_https(
                kba,
                "catalog_search_url_template",
            ),
        ),
        news_sources=_sources(news.get("sources"), brand_required=False),
        brand_news_sources=_sources(brand_news.get("sources"), brand_required=True),
        max_news_items_per_source=_positive(news, "max_items_per_source"),
    )
    _validate(config)
    return config


def _sources(value: object, *, brand_required: bool) -> tuple[NewsSourceConfig, ...]:
    if not isinstance(value, list):
        raise ValueError("news sources must be a list")
    sources = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each news source must be a mapping")
        brand_value = item.get("brand")
        brand = str(brand_value).strip() if brand_value is not None else None
        if brand_required and not brand:
            raise ValueError("brand news source requires brand")
        feed_value = item.get("feed_url")
        feed_url = str(feed_value).strip() if feed_value else None
        if feed_url is not None and not feed_url.startswith("https://"):
            raise ValueError("news feed URL must use HTTPS")
        sources.append(
            NewsSourceConfig(
                source_id=_text(item, "source_id"),
                source_name=_text(item, "source_name"),
                page_url=_https(item, "page_url"),
                feed_url=feed_url,
                country=_text(item, "country"),
                ttl_seconds=_positive(item, "ttl_seconds"),
                brand=brand,
            )
        )
    return tuple(sources)


def _validate(config: ExternalIntelligenceConfig) -> None:
    if config.http.timeout_seconds <= 0 or config.http.max_bytes <= 0:
        raise ValueError("HTTP limits must be positive")
    if config.kba.period_lag_months < 0 or config.kba.period_lag_months > 12:
        raise ValueError("KBA period_lag_months must be between 0 and 12")
    ids = [
        source.source_id
        for source in (*config.news_sources, *config.brand_news_sources)
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("external source IDs must be unique")
    required_brands = {item.brand for item in load_monitored_vehicles()}
    configured_brands = {
        source.brand for source in config.brand_news_sources if source.brand
    }
    missing = required_brands - configured_brands
    if missing:
        raise ValueError(
            "brand news configuration is missing: " + ", ".join(sorted(missing))
        )


def _mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"config key {key!r} must be a mapping")
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"config key {key!r} must be non-empty")
    return value


def _https(payload: dict[str, object], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise ValueError(f"config key {key!r} must use HTTPS")
    return value


def _optional_https(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None or not str(value).strip():
        return None
    url = str(value).strip()
    if not url.startswith("https://"):
        raise ValueError(f"config key {key!r} must use HTTPS")
    return url


def _positive(payload: dict[str, object], key: str) -> int:
    value = int(payload.get(key, 0))
    if value <= 0:
        raise ValueError(f"config key {key!r} must be positive")
    return value
