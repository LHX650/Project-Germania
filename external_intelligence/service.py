"""Provider composition and atomic unified external-intelligence output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.config import (
    DEFAULT_CONFIG_PATH,
    ExternalIntelligenceConfig,
    load_config,
)
from external_intelligence.http import HTTPFetcher, UrllibHTTPFetcher
from external_intelligence.kba import KBAOfficialProvider
from external_intelligence.news import OfficialBrandNewsProvider, RSSNewsProvider
from strategic.external import ExternalIntelligenceBundle


@dataclass(frozen=True)
class ExternalProviderSuite:
    """Concrete free/public external providers sharing one cache and HTTP client."""

    config: ExternalIntelligenceConfig
    kba: KBAOfficialProvider
    news: RSSNewsProvider
    brand_news: OfficialBrandNewsProvider


def build_provider_suite(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    fetcher: HTTPFetcher | None = None,
) -> ExternalProviderSuite:
    """Build default real providers without modifying collection orchestration."""

    config = load_config(config_path)
    cache = ExternalIntelligenceCache(config.cache_directory)
    http_fetcher = fetcher or UrllibHTTPFetcher(
        timeout_seconds=config.http.timeout_seconds,
        max_bytes=config.http.max_bytes,
        user_agent=config.http.user_agent,
    )
    return ExternalProviderSuite(
        config=config,
        kba=KBAOfficialProvider(
            config=config.kba,
            cache=cache,
            fetcher=http_fetcher,
        ),
        news=RSSNewsProvider(
            sources=config.news_sources,
            cache=cache,
            fetcher=http_fetcher,
            max_items_per_source=config.max_news_items_per_source,
        ),
        brand_news=OfficialBrandNewsProvider(
            sources=config.brand_news_sources,
            cache=cache,
            fetcher=http_fetcher,
            max_items_per_source=config.max_news_items_per_source,
        ),
    )


def write_external_intelligence_json(
    *,
    suite: ExternalProviderSuite,
    bundle: ExternalIntelligenceBundle,
    report_date: date,
    output_path: str | Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """Atomically write KBA, market news, and brand news in one JSON schema."""

    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    target = (
        Path(output_path or suite.config.output_path).expanduser().resolve(strict=False)
    )
    payload = {
        "schema_version": "1.0",
        "report_date": report_date.isoformat(),
        "generated_at": generated.isoformat(),
        "kba": {
            "status": bundle.kba.status.value,
            "provider": bundle.kba.provider_name,
            "records": [record.to_dict() for record in suite.kba.records],
            "limitations": list(bundle.kba.limitations),
        },
        "news": {
            "status": bundle.news.status.value,
            "provider": bundle.news.provider_name,
            "articles": [article.to_dict() for article in suite.news.articles],
            "limitations": list(bundle.news.limitations),
        },
        "brand_news": {
            "status": bundle.brand_news.status.value,
            "provider": bundle.brand_news.provider_name,
            "articles": [article.to_dict() for article in suite.brand_news.articles],
            "limitations": list(bundle.brand_news.limitations),
        },
        "sources": [
            run.to_dict()
            for run in (
                *suite.kba.source_runs,
                *suite.news.source_runs,
                *suite.brand_news.source_runs,
            )
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target
