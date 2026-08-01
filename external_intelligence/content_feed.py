"""Build an atomic News/Report/Video feed from attributed public metadata."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml

from external_intelligence.cache import ExternalIntelligenceCache
from external_intelligence.content_models import (
    ContentItem,
    ContentType,
    ImpactLevel,
    canonical_url,
    content_id,
)
from external_intelligence.content_parsing import (
    parse_govdata_reports,
    parse_official_report_page,
    parse_youtube_feed,
)
from external_intelligence.http import HTTPFetcher, UrllibHTTPFetcher
from external_intelligence.parsing import (
    parse_semantic_html_news,
    parse_structured_news,
)
from external_intelligence.recognition import recognize_entities

logger = logging.getLogger(__name__)
DEFAULT_EXTERNAL_INPUT = Path("reports/external_intelligence.json")
DEFAULT_ANALYTICS_INPUT = Path("reports/daily_market_intelligence.json")
DEFAULT_CONFIG = Path("config/content_sources.yaml")
DEFAULT_OUTPUT = Path("reports/external_intelligence/content_feed.json")


@dataclass(frozen=True)
class PublicContentSource:
    source_id: str
    source_name: str
    source_url: str
    region: str
    language: str
    ttl_seconds: int
    brand: str | None = None


@dataclass(frozen=True)
class ContentFeedResult:
    """Observable result from one independent feed build."""

    status: str
    output_path: str | None
    news_count: int
    report_count: int
    video_count: int
    source_statuses: tuple[dict[str, object], ...]
    error_message: str | None = None


def build_content_feed(
    *,
    external_input: str | Path = DEFAULT_EXTERNAL_INPUT,
    analytics_input: str | Path = DEFAULT_ANALYTICS_INPUT,
    config_path: str | Path = DEFAULT_CONFIG,
    output_path: str | Path | None = None,
    generated_at: datetime | None = None,
    fetcher: HTTPFetcher | None = None,
) -> ContentFeedResult:
    """Generate the unified feed while preserving an old file on failure."""

    try:
        external = _load_json(external_input)
        analytics = _load_json(analytics_input)
        config = _load_config(config_path)
        report_date = date.fromisoformat(_text(analytics, "date"))
        external_date = date.fromisoformat(_text(external, "report_date"))
        if external_date != report_date:
            raise ValueError("external and Analytics report dates do not match")
        generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
        report_end = datetime.combine(report_date, time.max, tzinfo=UTC)
        if generated < report_end:
            report_end = generated
        brands, vehicles = _tracked_entities(analytics)
        items, statuses = _upstream_news(
            external,
            cutoff=report_end,
            collected_at=generated,
        )
        fetched_items, fetched_statuses = _fetch_content_sources(
            config,
            year=report_date.year,
            cutoff=report_end,
            collected_at=generated,
            tracked_brands=brands,
            tracked_vehicles=vehicles,
            fetcher=fetcher,
        )
        items.extend(fetched_items)
        statuses.extend(fetched_statuses)
        deduplicated = _deduplicate(items)
        if not deduplicated and any(
            source.get("status") == "failed" for source in statuses
        ):
            raise RuntimeError(
                "all content evidence is unavailable after provider failures; "
                "the previous feed was preserved"
            )
        target = Path(output_path or config["output_path"]).resolve(strict=False)
        payload = {
            "schema_version": "1.0",
            "report_date": report_date.isoformat(),
            "generated_at": generated.isoformat(),
            "source_artifact": str(Path(external_input)),
            "counts": _counts(deduplicated),
            "items": [item.to_dict() for item in deduplicated],
            "sources": statuses,
        }
        _atomic_json(target, payload)
    except Exception as exc:
        logger.exception("Content feed generation failed")
        return ContentFeedResult(
            status="failed",
            output_path=None,
            news_count=0,
            report_count=0,
            video_count=0,
            source_statuses=(),
            error_message=f"{type(exc).__name__}: {exc}",
        )
    counts = _counts(deduplicated)
    return ContentFeedResult(
        status="completed",
        output_path=str(target),
        news_count=counts["news"],
        report_count=counts["report"],
        video_count=counts["video"],
        source_statuses=tuple(statuses),
    )


def _upstream_news(
    external: dict[str, Any],
    *,
    cutoff: datetime,
    collected_at: datetime,
) -> tuple[list[ContentItem], list[dict[str, object]]]:
    source_runs = {
        str(item.get("source")): item
        for item in _list(external.get("sources"), "sources")
        if isinstance(item, dict)
    }
    items: list[ContentItem] = []
    for section_name in ("news", "brand_news"):
        section = _mapping(external.get(section_name), section_name)
        for raw in _list(section.get("articles"), f"{section_name}.articles"):
            article = _mapping(raw, "article")
            published = _timestamp(article.get("published_at"), "published_at")
            if published > cutoff:
                continue
            source_name = _text(article, "source")
            source_run = source_runs.get(source_name, {})
            cache_status = str(source_run.get("cache_status") or "")
            brands = _strings(article.get("brands"))
            vehicles = _strings(article.get("models"))
            source_url = _text(article, "url")
            summary = _short(_text(article, "summary"))
            items.append(
                ContentItem(
                    content_id=content_id(ContentType.NEWS, source_url),
                    content_type=ContentType.NEWS,
                    title=_text(article, "title"),
                    source_name=source_name,
                    source_url=source_url,
                    published_at=published,
                    summary=summary,
                    language="und",
                    region=_text(article, "country"),
                    brands=brands,
                    vehicles=vehicles,
                    topics=_strings(article.get("tags")),
                    impact_level=_impact(brands, vehicles),
                    thumbnail_url=None,
                    document_url=None,
                    video_id=None,
                    collected_at=collected_at,
                    evidence_status=(
                        "stale_cache"
                        if cache_status == "stale_fallback"
                        else "verified_source"
                    ),
                    ai_summary=summary,
                    summary_mode="local_rule_fallback",
                )
            )
    return items, list(source_runs.values())


def _fetch_content_sources(
    config: dict[str, Any],
    *,
    year: int,
    cutoff: datetime,
    collected_at: datetime,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    fetcher: HTTPFetcher | None,
) -> tuple[list[ContentItem], list[dict[str, object]]]:
    http = _mapping(config.get("http"), "http")
    cache = ExternalIntelligenceCache(_text(config, "cache_directory"))
    http_fetcher = fetcher or UrllibHTTPFetcher(
        timeout_seconds=float(http.get("timeout_seconds", 20)),
        max_bytes=int(http.get("max_bytes", 25_000_000)),
        user_agent=_text(http, "user_agent"),
    )
    maximum = int(config.get("max_items_per_source", 20))
    items: list[ContentItem] = []
    statuses: list[dict[str, object]] = []
    for raw in _list(config.get("reports"), "reports"):
        raw_source = _mapping(raw, "report source")
        provider = str(raw_source.get("provider") or "govdata_ckan")
        source_key = (
            "source_url" if provider == "official_page" else "source_url_template"
        )
        source = _source(raw, key=source_key, year=year)
        try:
            entry = cache.get_or_fetch(
                source_id=source.source_id,
                source_url=source.source_url,
                ttl_seconds=source.ttl_seconds,
                fetcher=http_fetcher,
            )
            if provider == "official_page":
                page_items = _official_report_page_items(
                    source,
                    entry.payload_path.read_bytes(),
                    cache_status=entry.cache_status,
                    cutoff=cutoff,
                    collected_at=collected_at,
                    tracked_brands=tracked_brands,
                    tracked_vehicles=tracked_vehicles,
                    maximum=maximum,
                )
                items.extend(page_items)
                statuses.append(_status(source, entry.cache_status, len(page_items)))
                continue
            if provider != "govdata_ckan":
                raise ValueError(f"unsupported report provider: {provider}")
            records = parse_govdata_reports(entry.payload_path.read_bytes())
            accepted = 0
            for record in records:
                if record.published_at > cutoff or accepted >= maximum:
                    continue
                brands, vehicles = recognize_entities(
                    f"{record.title} {record.summary}",
                    tracked_brands=tracked_brands,
                    tracked_vehicles=tracked_vehicles,
                    source_brand=source.brand,
                )
                summary = _short(record.summary)
                items.append(
                    ContentItem(
                        content_id=content_id(ContentType.REPORT, record.source_url),
                        content_type=ContentType.REPORT,
                        title=record.title,
                        source_name=source.source_name,
                        source_url=record.source_url,
                        published_at=record.published_at,
                        summary=summary,
                        language=source.language,
                        region=source.region,
                        brands=brands,
                        vehicles=vehicles,
                        topics=record.topics,
                        impact_level=_impact(brands, vehicles, official_report=True),
                        thumbnail_url=None,
                        document_url=record.document_url,
                        video_id=None,
                        collected_at=collected_at,
                        evidence_status=_evidence(entry.cache_status),
                        ai_summary=summary,
                        summary_mode="local_rule_fallback",
                    )
                )
                accepted += 1
            statuses.append(_status(source, entry.cache_status, accepted))
        except Exception as exc:
            statuses.append(_failed_status(source, exc))
    for raw in _list(config.get("videos"), "videos"):
        source = _source(raw, key="feed_url", year=year)
        try:
            entry = cache.get_or_fetch(
                source_id=source.source_id,
                source_url=source.source_url,
                ttl_seconds=source.ttl_seconds,
                fetcher=http_fetcher,
            )
            records = parse_youtube_feed(entry.payload_path.read_bytes())
            accepted = 0
            for record in records:
                if record.published_at > cutoff or accepted >= maximum:
                    continue
                brands, vehicles = recognize_entities(
                    f"{record.title} {record.summary}",
                    tracked_brands=tracked_brands,
                    tracked_vehicles=tracked_vehicles,
                    source_brand=source.brand,
                )
                summary = _short(record.summary)
                items.append(
                    ContentItem(
                        content_id=content_id(ContentType.VIDEO, record.source_url),
                        content_type=ContentType.VIDEO,
                        title=record.title,
                        source_name=source.source_name,
                        source_url=record.source_url,
                        published_at=record.published_at,
                        summary=summary,
                        language=source.language,
                        region=source.region,
                        brands=brands,
                        vehicles=vehicles,
                        topics=("official video",),
                        impact_level=_impact(brands, vehicles),
                        thumbnail_url=record.thumbnail_url,
                        document_url=None,
                        video_id=record.video_id,
                        collected_at=collected_at,
                        evidence_status=_evidence(entry.cache_status),
                        ai_summary=summary,
                        summary_mode="local_rule_fallback",
                    )
                )
                accepted += 1
            statuses.append(_status(source, entry.cache_status, accepted))
        except Exception as exc:
            statuses.append(_failed_status(source, exc))
    return items, statuses


def _official_report_page_items(
    source: PublicContentSource,
    document: bytes,
    *,
    cache_status: str,
    cutoff: datetime,
    collected_at: datetime,
    tracked_brands: tuple[str, ...],
    tracked_vehicles: tuple[str, ...],
    maximum: int,
) -> list[ContentItem]:
    metadata = parse_official_report_page(document, page_url=source.source_url)
    if metadata is not None and metadata.published_at <= cutoff:
        brands, vehicles = recognize_entities(
            f"{metadata.title} {metadata.summary}",
            tracked_brands=tracked_brands,
            tracked_vehicles=tracked_vehicles,
            source_brand=source.brand,
        )
        summary = _short(metadata.summary)
        return [
            ContentItem(
                content_id=content_id(ContentType.REPORT, metadata.source_url),
                content_type=ContentType.REPORT,
                title=metadata.title,
                source_name=source.source_name,
                source_url=metadata.source_url,
                published_at=metadata.published_at,
                summary=summary,
                language=source.language,
                region=source.region,
                brands=brands,
                vehicles=vehicles,
                topics=tuple(sorted({*metadata.topics, "official report"})),
                impact_level=_impact(brands, vehicles, official_report=True),
                thumbnail_url=metadata.thumbnail_url,
                document_url=metadata.document_url,
                video_id=None,
                collected_at=collected_at,
                evidence_status=_evidence(cache_status),
                ai_summary=summary,
                summary_mode="local_rule_fallback",
            )
        ]
    articles = parse_structured_news(
        document,
        source=source.source_name,
        source_url=source.source_url,
        country=source.region,
        tracked_brands=tracked_brands,
        tracked_vehicles=tracked_vehicles,
        source_brand=source.brand,
        official_brand_news=False,
    )
    if not articles:
        articles = parse_semantic_html_news(
            document,
            source=source.source_name,
            source_url=source.source_url,
            country=source.region,
            tracked_brands=tracked_brands,
            tracked_vehicles=tracked_vehicles,
            source_brand=source.brand,
            official_brand_news=False,
        )
    items: list[ContentItem] = []
    for article in articles:
        if article.published_at > cutoff or len(items) >= maximum:
            continue
        summary = _short(article.summary)
        topics = tuple(sorted({*article.tags, "official report"}))
        items.append(
            ContentItem(
                content_id=content_id(ContentType.REPORT, article.url),
                content_type=ContentType.REPORT,
                title=article.title,
                source_name=source.source_name,
                source_url=article.url,
                published_at=article.published_at,
                summary=summary,
                language=source.language,
                region=source.region,
                brands=article.brands,
                vehicles=article.models,
                topics=topics,
                impact_level=_impact(
                    article.brands,
                    article.models,
                    official_report=True,
                ),
                thumbnail_url=None,
                document_url=article.url,
                video_id=None,
                collected_at=collected_at,
                evidence_status=_evidence(cache_status),
                ai_summary=summary,
                summary_mode="local_rule_fallback",
            )
        )
    if not items:
        raise ValueError("official report page exposed no dated report metadata")
    return items


def _load_config(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(
        Path(path).resolve(strict=True).read_text(encoding="utf-8")
    )
    config = _mapping(payload, "content config")
    for key in ("output_path", "cache_directory", "http", "reports", "videos"):
        if key not in config:
            raise ValueError(f"content config is missing {key}")
    return config


def _source(raw: object, *, key: str, year: int) -> PublicContentSource:
    item = _mapping(raw, "content source")
    url = _text(item, key).format(year=year)
    if not url.startswith("https://"):
        raise ValueError("content source URL must use HTTPS")
    ttl = int(item.get("ttl_seconds", 0))
    if ttl <= 0:
        raise ValueError("content source TTL must be positive")
    brand = str(item.get("brand") or "").strip() or None
    return PublicContentSource(
        source_id=_text(item, "source_id"),
        source_name=_text(item, "source_name"),
        source_url=url,
        region=_text(item, "region"),
        language=_text(item, "language"),
        ttl_seconds=ttl,
        brand=brand,
    )


def _tracked_entities(
    analytics: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    brands: set[str] = set()
    vehicles: set[str] = set()
    for raw in _list(analytics.get("vehicles"), "vehicles"):
        item = _mapping(raw, "vehicle item")
        identity = _mapping(item.get("vehicle"), "vehicle")
        brand = _text(identity, "brand")
        model = _text(identity, "model")
        brands.add(brand)
        vehicles.add(f"{brand} {model}")
    return tuple(sorted(brands)), tuple(sorted(vehicles))


def _deduplicate(items: list[ContentItem]) -> list[ContentItem]:
    by_url: dict[str, ContentItem] = {}
    for item in sorted(items, key=lambda value: value.published_at):
        key = canonical_url(item.source_url)
        current = by_url.get(key)
        if current is None or _type_priority(item.content_type) > _type_priority(
            current.content_type
        ):
            by_url[key] = item
    return sorted(by_url.values(), key=lambda item: item.published_at, reverse=True)


def _type_priority(value: ContentType) -> int:
    return {ContentType.NEWS: 1, ContentType.VIDEO: 2, ContentType.REPORT: 3}[value]


def _impact(
    brands: tuple[str, ...],
    vehicles: tuple[str, ...],
    *,
    official_report: bool = False,
) -> ImpactLevel:
    if vehicles or official_report:
        return ImpactLevel.HIGH
    if brands:
        return ImpactLevel.MEDIUM
    return ImpactLevel.LOW


def _evidence(cache_status: str) -> str:
    return "stale_cache" if cache_status == "stale_fallback" else "verified_source"


def _status(
    source: PublicContentSource,
    cache_status: str,
    count: int,
) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_name": source.source_name,
        "source_url": source.source_url,
        "status": "available",
        "cache_status": cache_status,
        "record_count": count,
        "limitation": (
            "Expired cache used after refresh failure."
            if cache_status == "stale_fallback"
            else None
        ),
    }


def _failed_status(
    source: PublicContentSource,
    exc: Exception,
) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_name": source.source_name,
        "source_url": source.source_url,
        "status": "failed",
        "cache_status": None,
        "record_count": 0,
        "limitation": f"{type(exc).__name__}: {exc}",
    }


def _counts(items: list[ContentItem]) -> dict[str, int]:
    return {
        kind.value: sum(item.content_type is kind for item in items)
        for kind in ContentType
    }


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).resolve(strict=True).read_text(encoding="utf-8"))
    return _mapping(payload, str(path))


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array")
    return value


def _text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} must be non-empty")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must use ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _short(value: str) -> str:
    return " ".join(value.split())[:600]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the independent content feed stage and print its status."""

    parser = argparse.ArgumentParser(
        description="Build the public automotive content feed."
    )
    parser.add_argument("--external-input", type=Path, default=DEFAULT_EXTERNAL_INPUT)
    parser.add_argument("--analytics-input", type=Path, default=DEFAULT_ANALYTICS_INPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = build_content_feed(
        external_input=args.external_input,
        analytics_input=args.analytics_input,
        config_path=args.config,
        output_path=args.output,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
