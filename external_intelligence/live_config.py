"""Validated configuration for live external automotive intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

LiveProviderKind = Literal[
    "automotive_news",
    "policy_regulation",
    "official_brand_news",
    "industry_report",
]

DEFAULT_LIVE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "live_external_intelligence.yaml"
)
_PROVIDER_KINDS = frozenset(
    {
        "automotive_news",
        "policy_regulation",
        "official_brand_news",
        "industry_report",
    }
)


@dataclass(frozen=True)
class LiveHTTPConfig:
    """Bounded HTTP settings for public no-auth sources."""

    timeout_seconds: float
    max_bytes: int
    user_agent: str


@dataclass(frozen=True)
class LiveSourceConfig:
    """One attributed RSS, API, or official public-data source."""

    source_id: str
    source_name: str
    provider_kind: LiveProviderKind
    page_url: str
    feed_url: str | None
    transport: str
    region: str
    category: str
    evidence_type: str
    reliability: float
    ttl_seconds: int
    brand: str | None = None


@dataclass(frozen=True)
class LiveExternalConfig:
    """Complete independent configuration for the Phase 18B live layer."""

    cache_directory: Path
    recent_days: int
    max_items_per_provider: int
    http: LiveHTTPConfig
    sources: tuple[LiveSourceConfig, ...]


def load_live_config(
    path: str | Path = DEFAULT_LIVE_CONFIG_PATH,
) -> LiveExternalConfig:
    """Load and validate live-source configuration without making requests."""

    config_path = Path(path).expanduser().resolve(strict=True)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("live external intelligence config must be a mapping")
    defaults = _mapping(payload, "defaults")
    http = _mapping(payload, "http")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("live external sources must be a list")
    sources = tuple(_source(item) for item in raw_sources)
    source_ids = tuple(item.source_id for item in sources)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("live external source IDs must be unique")
    configured_kinds = {item.provider_kind for item in sources}
    missing_kinds = _PROVIDER_KINDS - configured_kinds
    if missing_kinds:
        raise ValueError(
            "live external provider kinds are missing: "
            + ", ".join(sorted(missing_kinds))
        )
    recent_days = int(defaults.get("recent_days", 30))
    max_items = int(defaults.get("max_items_per_provider", 12))
    if recent_days <= 0 or max_items <= 0:
        raise ValueError("live external recent_days and max items must be positive")
    cache_directory = Path(_text(defaults, "cache_directory"))
    if not cache_directory.is_absolute():
        cache_directory = config_path.parents[1] / cache_directory
    return LiveExternalConfig(
        cache_directory=cache_directory.resolve(strict=False),
        recent_days=recent_days,
        max_items_per_provider=max_items,
        http=LiveHTTPConfig(
            timeout_seconds=float(http.get("timeout_seconds", 12)),
            max_bytes=int(http.get("max_bytes", 5_000_000)),
            user_agent=_text(http, "user_agent"),
        ),
        sources=sources,
    )


def _source(value: object) -> LiveSourceConfig:
    if not isinstance(value, dict):
        raise ValueError("each live external source must be a mapping")
    provider_kind = _text(value, "provider_kind")
    if provider_kind not in _PROVIDER_KINDS:
        raise ValueError(f"unsupported live provider kind: {provider_kind}")
    transport = str(value.get("transport", "rss_or_html")).strip().casefold()
    if transport not in {"rss_or_html", "api", "official_public_data"}:
        raise ValueError(f"unsupported live source transport: {transport}")
    page_url = _https(value, "page_url")
    feed_value = value.get("feed_url")
    feed_url = _https_value(feed_value, "feed_url") if feed_value else None
    reliability = float(value.get("reliability", 0))
    if reliability < 0 or reliability > 100:
        raise ValueError("live source reliability must be between 0 and 100")
    ttl_seconds = int(value.get("ttl_seconds", 0))
    if ttl_seconds <= 0:
        raise ValueError("live source ttl_seconds must be positive")
    brand_value = value.get("brand")
    brand = str(brand_value).strip() if brand_value is not None else None
    if provider_kind == "official_brand_news" and not brand:
        raise ValueError("official brand source requires a brand")
    return LiveSourceConfig(
        source_id=_text(value, "source_id"),
        source_name=_text(value, "source_name"),
        provider_kind=provider_kind,  # type: ignore[arg-type]
        page_url=page_url,
        feed_url=feed_url,
        transport=transport,
        region=_text(value, "region"),
        category=_text(value, "category"),
        evidence_type=_text(value, "evidence_type"),
        reliability=reliability,
        ttl_seconds=ttl_seconds,
        brand=brand,
    )


def _mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"live config key {key!r} must be a mapping")
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"live config key {key!r} must be non-empty")
    return value


def _https(payload: dict[str, object], key: str) -> str:
    return _https_value(_text(payload, key), key)


def _https_value(value: object, key: str) -> str:
    url = str(value).strip()
    if not url.startswith("https://"):
        raise ValueError(f"live config key {key!r} must use HTTPS")
    return url
