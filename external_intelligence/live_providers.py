"""Live, source-attributed automotive intelligence provider adapters."""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import ExternalQuery, IntelligenceProviderError
from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.config import NewsSourceConfig
from external_intelligence.http import HTTPFetcher, UrllibHTTPFetcher
from external_intelligence.live_config import (
    DEFAULT_LIVE_CONFIG_PATH,
    LiveExternalConfig,
    LiveProviderKind,
    LiveSourceConfig,
    load_live_config,
)
from external_intelligence.news import OfficialBrandNewsProvider, RSSNewsProvider
from external_intelligence.recognition import recognize_entities
from strategic.external import (
    ExternalIntelligenceRequest,
    ExternalSourceStatus,
)

logger = logging.getLogger(__name__)
_SPACE_PATTERN = re.compile(r"\s+")
_HTML_PATTERN = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class LiveProviderResult:
    """One provider's evidence and isolated source-level status."""

    provider_name: str
    provider_kind: str
    status: str
    evidence: tuple[ExternalEvidence, ...]
    successful_sources: tuple[str, ...]
    failed_sources: tuple[str, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class LiveExternalCollection:
    """Deduplicated live evidence plus every provider's observable outcome."""

    fetched_at: datetime
    evidence: tuple[ExternalEvidence, ...]
    providers: tuple[LiveProviderResult, ...]


class LiveExternalProvider:
    """Common bounded implementation for one external evidence category."""

    def __init__(
        self,
        *,
        provider_kind: LiveProviderKind,
        sources: tuple[LiveSourceConfig, ...],
        cache: ExternalIntelligenceCache,
        fetcher: HTTPFetcher,
        recent_days: int,
        max_items: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not sources or any(item.provider_kind != provider_kind for item in sources):
            raise ValueError("live provider sources must match its provider kind")
        if recent_days <= 0 or max_items <= 0:
            raise ValueError("live provider bounds must be positive")
        self.provider_kind = provider_kind
        self.sources = sources
        self.cache = cache
        self.fetcher = fetcher
        self.recent_days = recent_days
        self.max_items = max_items
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        """Return a stable provider identifier."""

        return f"live_{self.provider_kind}"

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the unified capability implemented by this provider."""

        return frozenset({self.provider_kind})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Return verified recent evidence or fail for complete source outage."""

        result = self.fetch(query)
        if result.status == "failed":
            raise IntelligenceProviderError(
                "; ".join(result.errors) or f"{self.name} failed"
            )
        return result.evidence

    def fetch(self, query: ExternalQuery) -> LiveProviderResult:
        """Fetch configured sources concurrently with per-source failure isolation."""

        now = self._clock().astimezone(UTC)
        evidence: list[ExternalEvidence] = []
        successful: list[str] = []
        failed: list[str] = []
        errors: list[str] = []
        worker_count = min(4, len(self.sources))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(self._fetch_source, source, query, now): source
                for source in self.sources
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    source_evidence = future.result()
                except Exception as exc:
                    message = f"{source.source_name}: {type(exc).__name__}: {exc}"
                    logger.warning("Live external source failed: %s", message)
                    failed.append(source.source_name)
                    errors.append(message)
                    continue
                successful.append(source.source_name)
                evidence.extend(source_evidence)
        deduplicated = _deduplicate(evidence, self.max_items)
        if failed and not successful:
            status = "failed"
        elif failed:
            status = "partial"
        elif deduplicated:
            status = "available"
        else:
            status = "insufficient_data"
        return LiveProviderResult(
            provider_name=self.name,
            provider_kind=self.provider_kind,
            status=status,
            evidence=deduplicated,
            successful_sources=tuple(sorted(successful)),
            failed_sources=tuple(sorted(failed)),
            errors=tuple(errors),
        )

    def _fetch_source(
        self,
        source: LiveSourceConfig,
        query: ExternalQuery,
        now: datetime,
    ) -> tuple[ExternalEvidence, ...]:
        if source.transport == "api":
            return self._fetch_api_source(source, query, now)
        return self._fetch_feed_source(source, query, now)

    def _fetch_feed_source(
        self,
        source: LiveSourceConfig,
        query: ExternalQuery,
        now: datetime,
    ) -> tuple[ExternalEvidence, ...]:
        news_source = NewsSourceConfig(
            source_id=source.source_id,
            source_name=source.source_name,
            page_url=source.page_url,
            feed_url=source.feed_url,
            country=source.region,
            ttl_seconds=source.ttl_seconds,
            brand=source.brand,
        )
        provider_type = (
            OfficialBrandNewsProvider
            if self.provider_kind == "official_brand_news"
            else RSSNewsProvider
        )
        provider = provider_type(
            sources=(news_source,),
            cache=self.cache,
            fetcher=self.fetcher,
            max_items_per_source=self.max_items,
        )
        request = ExternalIntelligenceRequest(
            report_date=now.date(),
            brands=query.brands,
            vehicles=query.vehicles,
        )
        snapshot = (
            provider.fetch_brand_news(request)
            if isinstance(provider, OfficialBrandNewsProvider)
            else provider.fetch_news(request)
        )
        if snapshot.status is ExternalSourceStatus.FAILED:
            raise IntelligenceProviderError(
                snapshot.error_message or "source returned failed status"
            )
        source_run = next(iter(provider.source_runs), None)
        fetched_time = (
            source_run.updated_at
            if source_run is not None and source_run.updated_at is not None
            else now
        )
        reliability = (
            min(source.reliability, 70.0)
            if source_run is not None and source_run.cache_status == "stale_fallback"
            else source.reliability
        )
        return tuple(
            evidence
            for article in provider.articles
            if (
                evidence := _article_evidence(
                    article=article,
                    source=source,
                    fetched_time=fetched_time,
                    query=query,
                    now=now,
                    recent_days=self.recent_days,
                    reliability=reliability,
                )
            )
            is not None
        )

    def _fetch_api_source(
        self,
        source: LiveSourceConfig,
        query: ExternalQuery,
        now: datetime,
    ) -> tuple[ExternalEvidence, ...]:
        entry = self.cache.get_or_fetch(
            source_id=source.source_id,
            source_url=source.page_url,
            ttl_seconds=source.ttl_seconds,
            fetcher=self.fetcher,
            now=now,
        )
        payload = json.loads(entry.payload_path.read_text(encoding="utf-8"))
        return tuple(
            evidence
            for item in _api_items(payload)
            if (
                evidence := _api_evidence(
                    item=item,
                    source=source,
                    fetched_time=entry.fetched_at,
                    query=query,
                    now=now,
                    recent_days=self.recent_days,
                    reliability=(
                        min(source.reliability, 70.0)
                        if entry.cache_status == "stale_fallback"
                        else source.reliability
                    ),
                )
            )
            is not None
        )


class AutomotiveNewsLiveProvider(LiveExternalProvider):
    """Live automotive-news provider for official association sources."""


class PolicyRegulationLiveProvider(LiveExternalProvider):
    """Live policy and regulation provider for official government sources."""


class OfficialBrandNewsLiveProvider(LiveExternalProvider):
    """Live official-brand newsroom provider."""


class IndustryReportLiveProvider(LiveExternalProvider):
    """Live industry-report and official public-data provider."""


def build_live_providers(
    config_path: str = str(DEFAULT_LIVE_CONFIG_PATH),
    *,
    fetcher: HTTPFetcher | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[LiveExternalProvider, ...]:
    """Build all four provider categories without performing a request."""

    config = load_live_config(config_path)
    return build_live_providers_from_config(config, fetcher=fetcher, clock=clock)


def build_live_providers_from_config(
    config: LiveExternalConfig,
    *,
    fetcher: HTTPFetcher | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[LiveExternalProvider, ...]:
    """Build live providers from validated config for production or tests."""

    cache = ExternalIntelligenceCache(config.cache_directory)
    http_fetcher = fetcher or UrllibHTTPFetcher(
        timeout_seconds=config.http.timeout_seconds,
        max_bytes=config.http.max_bytes,
        user_agent=config.http.user_agent,
    )
    classes = {
        "automotive_news": AutomotiveNewsLiveProvider,
        "policy_regulation": PolicyRegulationLiveProvider,
        "official_brand_news": OfficialBrandNewsLiveProvider,
        "industry_report": IndustryReportLiveProvider,
    }
    return tuple(
        classes[kind](
            provider_kind=kind,  # type: ignore[arg-type]
            sources=tuple(
                item for item in config.sources if item.provider_kind == kind
            ),
            cache=cache,
            fetcher=http_fetcher,
            recent_days=config.recent_days,
            max_items=config.max_items_per_provider,
            clock=clock,
        )
        for kind in classes
    )


def collect_live_external_intelligence(
    providers: tuple[LiveExternalProvider, ...],
    query: ExternalQuery,
    *,
    fetched_at: datetime | None = None,
) -> LiveExternalCollection:
    """Collect provider results independently and deduplicate URLs globally."""

    results: list[LiveProviderResult] = []
    worker_count = min(4, len(providers)) if providers else 1
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(provider.fetch, query): provider for provider in providers
        }
        for future in as_completed(futures):
            provider = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    LiveProviderResult(
                        provider_name=provider.name,
                        provider_kind=provider.provider_kind,
                        status="failed",
                        evidence=(),
                        successful_sources=(),
                        failed_sources=tuple(
                            source.source_name for source in provider.sources
                        ),
                        errors=(f"{type(exc).__name__}: {exc}",),
                    )
                )
    ordered = tuple(sorted(results, key=lambda item: item.provider_kind))
    evidence = _deduplicate(
        [item for result in ordered for item in result.evidence],
        sum(provider.max_items for provider in providers),
    )
    return LiveExternalCollection(
        fetched_at=(fetched_at or datetime.now(UTC)).astimezone(UTC),
        evidence=evidence,
        providers=ordered,
    )


def _article_evidence(
    *,
    article: Any,
    source: LiveSourceConfig,
    fetched_time: datetime,
    query: ExternalQuery,
    now: datetime,
    recent_days: int,
    reliability: float,
) -> ExternalEvidence | None:
    if not _in_time_window(article.published_at, now, recent_days):
        return None
    if not _relevant(
        title=article.title,
        summary=article.summary,
        brands=article.brands,
        vehicles=article.models,
        query=query,
    ):
        return None
    return ExternalEvidence(
        source=source.source_name,
        title=article.title,
        url=article.url,
        published_date=article.published_at.isoformat(),
        category=source.category,
        brand=", ".join(article.brands) or source.brand,
        vehicle=", ".join(article.models) or None,
        content_summary=_short_summary(article.summary),
        reliability=reliability,
        fetched_time=fetched_time.astimezone(UTC).isoformat(),
        evidence_type=source.evidence_type,
        region=source.region,
    )


def _api_evidence(
    *,
    item: dict[str, Any],
    source: LiveSourceConfig,
    fetched_time: datetime,
    query: ExternalQuery,
    now: datetime,
    recent_days: int,
    reliability: float,
) -> ExternalEvidence | None:
    title = _first_text(item, "title", "headline", "name")
    url_value = _first_text(item, "url", "link", "source_url")
    published_text = _first_text(
        item,
        "published_date",
        "published_at",
        "date",
        "updated_at",
    )
    published = _parse_datetime(published_text)
    if not title or not url_value or published is None:
        return None
    url = urljoin(source.page_url, url_value)
    if not url.startswith("https://") or not _in_time_window(
        published, now, recent_days
    ):
        return None
    summary = _clean_text(
        _first_text(item, "content_summary", "summary", "description") or title
    )
    text = f"{title} {summary}"
    brands, vehicles = recognize_entities(
        text,
        tracked_brands=query.brands,
        tracked_vehicles=query.vehicles,
        source_brand=source.brand,
    )
    if not _relevant(
        title=title,
        summary=summary,
        brands=brands,
        vehicles=vehicles,
        query=query,
    ):
        return None
    return ExternalEvidence(
        source=source.source_name,
        title=_clean_text(title),
        url=url,
        published_date=published.isoformat(),
        category=source.category,
        brand=", ".join(brands) or source.brand,
        vehicle=", ".join(vehicles) or None,
        content_summary=_short_summary(summary),
        reliability=reliability,
        fetched_time=fetched_time.astimezone(UTC).isoformat(),
        evidence_type=source.evidence_type,
        region=source.region,
    )


def _api_items(payload: object) -> tuple[dict[str, Any], ...]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = next(
            (
                value
                for key in ("items", "results", "data", "articles", "records")
                if isinstance((value := payload.get(key)), list)
            ),
            [],
        )
    else:
        return ()
    return tuple(item for item in values if isinstance(item, dict))


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _in_time_window(published: datetime, now: datetime, recent_days: int) -> bool:
    observed = published.astimezone(UTC)
    return now - timedelta(days=recent_days) <= observed <= now


def _relevant(
    *,
    title: str,
    summary: str,
    brands: tuple[str, ...],
    vehicles: tuple[str, ...],
    query: ExternalQuery,
) -> bool:
    if not query.query.strip():
        return True
    terms = {
        term
        for term in _normalize(query.query).split()
        if len(term) >= 3 and term not in {"what", "which", "why", "main", "market"}
    }
    requested_brands = {_normalize(value) for value in query.brands}
    requested_vehicles = {_normalize(value) for value in query.vehicles}
    searchable = _normalize(" ".join((title, summary, *brands, *vehicles)))
    if not terms and not requested_brands and not requested_vehicles:
        return True
    return bool(
        any(term in searchable for term in terms)
        or requested_brands.intersection(_normalize(value) for value in brands)
        or requested_vehicles.intersection(_normalize(value) for value in vehicles)
    )


def _deduplicate(
    evidence: list[ExternalEvidence],
    limit: int,
) -> tuple[ExternalEvidence, ...]:
    by_url: dict[str, ExternalEvidence] = {}
    for item in sorted(
        evidence,
        key=lambda value: (value.published_date, value.reliability),
        reverse=True,
    ):
        by_url.setdefault(item.url, item)
    return tuple(by_url.values())[:limit]


def _short_summary(value: str, limit: int = 600) -> str:
    cleaned = _clean_text(value)
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1].rstrip()}…"


def _clean_text(value: str) -> str:
    return _SPACE_PATTERN.sub(" ", html.unescape(_HTML_PATTERN.sub(" ", value))).strip()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())
