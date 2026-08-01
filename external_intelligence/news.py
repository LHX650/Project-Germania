"""RSS-first general and official brand-news providers."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, time

from external_intelligence.cache import CacheEntry, ExternalIntelligenceCache
from external_intelligence.config import NewsSourceConfig
from external_intelligence.http import HTTPFetcher
from external_intelligence.models import NewsArticle, SourceRun
from external_intelligence.parsing import (
    discover_feed_url,
    parse_feed,
    parse_semantic_html_news,
    parse_structured_news,
)
from strategic.external import (
    ExternalIntelligenceRequest,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SourceResult:
    articles: tuple[NewsArticle, ...]
    run: SourceRun


class RSSNewsProvider:
    """Read configured public RSS/Atom market-news sources."""

    name = "rss_market_news"

    def __init__(
        self,
        *,
        sources: tuple[NewsSourceConfig, ...],
        cache: ExternalIntelligenceCache,
        fetcher: HTTPFetcher,
        max_items_per_source: int,
    ) -> None:
        self.sources = sources
        self.cache = cache
        self.fetcher = fetcher
        self.max_items_per_source = max_items_per_source
        self.articles: tuple[NewsArticle, ...] = ()
        self.source_runs: tuple[SourceRun, ...] = ()

    def fetch_news(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return attributed general-market RSS signals."""

        return self._fetch(request, ExternalSourceType.NEWS, official=False)

    def _fetch(
        self,
        request: ExternalIntelligenceRequest,
        source_type: ExternalSourceType,
        *,
        official: bool,
    ) -> ExternalSourceSnapshot:
        articles: list[NewsArticle] = []
        runs: list[SourceRun] = []
        failures: list[str] = []
        for source in self.sources:
            try:
                result = _fetch_source(
                    source,
                    request=request,
                    cache=self.cache,
                    fetcher=self.fetcher,
                    max_items=self.max_items_per_source,
                    official=official,
                )
            except Exception as exc:
                error = f"{source.source_name}: {type(exc).__name__}: {exc}"
                logger.warning("External news source failed: %s", error)
                failures.append(error)
                runs.append(
                    SourceRun(
                        source_id=source.source_id,
                        source=source.source_name,
                        source_url=source.page_url,
                        status="failed",
                        cache_status=None,
                        updated_at=None,
                        ttl_seconds=source.ttl_seconds,
                        record_count=0,
                        limitation=error,
                    )
                )
                continue
            articles.extend(result.articles)
            runs.append(result.run)
        by_id = {article.article_id: article for article in articles}
        self.articles = tuple(
            sorted(
                by_id.values(),
                key=lambda item: item.published_at,
                reverse=True,
            )
        )
        self.source_runs = tuple(runs)
        if not runs or all(run.status == "failed" for run in runs):
            return ExternalSourceSnapshot(
                source_type=source_type,
                provider_name=self.name,
                status=ExternalSourceStatus.FAILED,
                limitations=tuple(failures) or ("No news sources are configured.",),
                error_message="; ".join(failures) or "no configured sources",
            )
        limitations = list(failures)
        limitations.extend(
            run.limitation for run in runs if run.limitation and run.status != "failed"
        )
        return ExternalSourceSnapshot(
            source_type=source_type,
            provider_name=self.name,
            status=ExternalSourceStatus.AVAILABLE,
            signals=tuple(_news_signal(article) for article in self.articles),
            limitations=tuple(limitations),
        )


class OfficialBrandNewsProvider(RSSNewsProvider):
    """RSS-first provider for six configured official manufacturer newsrooms."""

    name = "official_brand_news"

    def fetch_brand_news(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return official manufacturer news with source brand attribution."""

        return self._fetch(request, ExternalSourceType.BRAND_NEWS, official=True)


def _fetch_source(
    source: NewsSourceConfig,
    *,
    request: ExternalIntelligenceRequest,
    cache: ExternalIntelligenceCache,
    fetcher: HTTPFetcher,
    max_items: int,
    official: bool,
) -> _SourceResult:
    page_entry: CacheEntry | None = None
    feed_url = source.feed_url
    if feed_url is None:
        page_entry = cache.get_or_fetch(
            source_id=f"{source.source_id}_page",
            source_url=source.page_url,
            ttl_seconds=source.ttl_seconds,
            fetcher=fetcher,
        )
        document = page_entry.payload_path.read_bytes()
        feed_url = discover_feed_url(document, source.page_url)
        if feed_url is None:
            parsed = parse_structured_news(
                document,
                source=source.source_name,
                source_url=source.page_url,
                country=source.country,
                tracked_brands=request.brands,
                tracked_vehicles=request.vehicles,
                source_brand=source.brand,
                official_brand_news=official,
            )
            if not parsed:
                parsed = parse_semantic_html_news(
                    document,
                    source=source.source_name,
                    source_url=source.page_url,
                    country=source.country,
                    tracked_brands=request.brands,
                    tracked_vehicles=request.vehicles,
                    source_brand=source.brand,
                    official_brand_news=official,
                )
            articles = _bounded(parsed, request, max_items)
            limitation = (
                "No RSS/Atom autodiscovery link was exposed; JSON-LD "
                "NewsArticle or dated semantic-HTML fallback was used."
            )
            if not articles:
                limitation += " No dated article was available."
            return _SourceResult(
                articles=articles,
                run=_source_run(
                    source,
                    page_entry,
                    len(articles),
                    limitation=limitation,
                ),
            )
    feed_entry = cache.get_or_fetch(
        source_id=f"{source.source_id}_feed",
        source_url=feed_url,
        ttl_seconds=source.ttl_seconds,
        fetcher=fetcher,
    )
    parsed = parse_feed(
        feed_entry.payload_path.read_bytes(),
        source=source.source_name,
        source_url=source.page_url,
        country=source.country,
        tracked_brands=request.brands,
        tracked_vehicles=request.vehicles,
        source_brand=source.brand,
        official_brand_news=official,
    )
    articles = _bounded(parsed, request, max_items)
    statuses = [feed_entry.cache_status]
    if page_entry is not None:
        statuses.append(page_entry.cache_status)
    limitation = (
        "Expired cached content was used because refresh failed."
        if "stale_fallback" in statuses
        else None
    )
    return _SourceResult(
        articles=articles,
        run=_source_run(source, feed_entry, len(articles), limitation=limitation),
    )


def _bounded(
    articles: tuple[NewsArticle, ...],
    request: ExternalIntelligenceRequest,
    max_items: int,
) -> tuple[NewsArticle, ...]:
    report_end = datetime.combine(
        request.report_date,
        time.max,
        tzinfo=articles[0].published_at.tzinfo if articles else None,
    )
    return tuple(article for article in articles if article.published_at <= report_end)[
        :max_items
    ]


def _source_run(
    source: NewsSourceConfig,
    entry: CacheEntry,
    count: int,
    *,
    limitation: str | None,
) -> SourceRun:
    return SourceRun(
        source_id=source.source_id,
        source=source.source_name,
        source_url=source.page_url,
        status="available",
        cache_status=entry.cache_status,
        updated_at=entry.fetched_at,
        ttl_seconds=source.ttl_seconds,
        record_count=count,
        limitation=limitation,
    )


def _news_signal(article: NewsArticle) -> ExternalSignal:
    entity = (
        article.models[0]
        if article.models
        else (article.brands[0] if article.brands else None)
    )
    return ExternalSignal(
        signal_id=hashlib.sha256(article.article_id.encode()).hexdigest()[:24],
        title=article.title,
        summary=article.summary,
        implication=StrategicImplication.CONTEXT,
        source_url=article.url,
        observed_at=article.published_at,
        entity=entity,
    )
