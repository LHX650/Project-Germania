"""Validated, modification-aware access to the unified public content feed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.intelligence import DailyMarketIntelligence, VehicleIntelligence
from services.runtime import get_dashboard_data_paths

DEFAULT_CONTENT_FEED = Path("reports/external_intelligence/content_feed.json")


class ContentFeedError(RuntimeError):
    """Raised when the read-only content artifact is missing or invalid."""


@dataclass(frozen=True)
class ContentRecord:
    """One validated card/detail record for the content hub."""

    content_id: str
    content_type: str
    title: str
    source_name: str
    source_url: str
    published_at: datetime
    summary: str
    language: str
    region: str
    brands: tuple[str, ...]
    vehicles: tuple[str, ...]
    topics: tuple[str, ...]
    impact_level: str
    thumbnail_url: str | None
    document_url: str | None
    video_id: str | None
    collected_at: datetime
    evidence_status: str
    ai_summary: str | None
    summary_mode: str


@dataclass(frozen=True)
class ContentFeed:
    """Current unified content feed and its source health."""

    report_date: date
    generated_at: datetime
    counts: dict[str, int]
    items: tuple[ContentRecord, ...]
    sources: tuple[dict[str, object], ...]
    source_path: Path


@dataclass(frozen=True)
class MarketValidation:
    """Exact vehicle match to existing Analytics metrics."""

    vehicle_name: str
    active_listing_count: int
    price_change_7d_pct: float | None
    inventory_change_7d_count: int
    opportunity_score: float


def load_content_feed(path: str | Path | None = None) -> ContentFeed:
    """Load the feed and invalidate the bounded cache after file changes."""

    resolved = _resolve(path)
    if not resolved.is_file():
        raise ContentFeedError(
            "The content feed has not been generated: "
            "reports/external_intelligence/content_feed.json"
        )
    stat = resolved.stat()
    return _load_cached(str(resolved), stat.st_mtime_ns, stat.st_size)


def clear_content_feed_cache() -> None:
    """Clear the bounded file cache, primarily for tests."""

    _load_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_cached(path_text: str, modified_at_ns: int, size: int) -> ContentFeed:
    del modified_at_ns, size
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentFeedError("The content feed is not valid UTF-8 JSON.") from exc
    return _parse_feed(payload, path)


def filter_content(
    items: tuple[ContentRecord, ...],
    *,
    keyword: str = "",
    content_types: tuple[str, ...] = (),
    sources: tuple[str, ...] = (),
    brands: tuple[str, ...] = (),
    vehicles: tuple[str, ...] = (),
    regions: tuple[str, ...] = (),
    topics: tuple[str, ...] = (),
    impact_levels: tuple[str, ...] = (),
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[ContentRecord, ...]:
    """Apply all content-center filters without mutating source data."""

    needle = " ".join(keyword.casefold().split())
    filtered = []
    for item in items:
        searchable = " ".join(
            (
                item.title,
                item.summary,
                item.source_name,
                *item.brands,
                *item.vehicles,
                *item.topics,
            )
        ).casefold()
        published_date = item.published_at.date()
        if needle and needle not in searchable:
            continue
        if content_types and item.content_type not in content_types:
            continue
        if sources and item.source_name not in sources:
            continue
        if brands and not set(brands).intersection(item.brands):
            continue
        if vehicles and not set(vehicles).intersection(item.vehicles):
            continue
        if regions and item.region not in regions:
            continue
        if topics and not set(topics).intersection(item.topics):
            continue
        if impact_levels and item.impact_level not in impact_levels:
            continue
        if start_date is not None and published_date < start_date:
            continue
        if end_date is not None and published_date > end_date:
            continue
        filtered.append(item)
    return tuple(filtered)


def match_market_metrics(
    item: ContentRecord,
    report: DailyMarketIntelligence | None,
) -> MarketValidation | None:
    """Return only an unambiguous exact vehicle-level Analytics match."""

    if report is None:
        return None
    exact_names = {_normalized(value) for value in item.vehicles}
    matched = [
        vehicle
        for vehicle in report.vehicles
        if _normalized(f"{vehicle.brand} {vehicle.model}") in exact_names
    ]
    if not matched and item.brands:
        brand_names = {_normalized(value) for value in item.brands}
        brand_matches = [
            vehicle
            for vehicle in report.vehicles
            if _normalized(vehicle.brand) in brand_names
        ]
        if len(brand_matches) == 1:
            matched = brand_matches
    if len(matched) != 1:
        return None
    return _market_validation(matched[0])


def resolve_thumbnail_url(item: ContentRecord) -> str | None:
    """Return a source-bound card image, preferring stored provider metadata."""

    if item.thumbnail_url is not None:
        return item.thumbnail_url
    if item.content_type == "video" and item.video_id is not None:
        return f"https://i.ytimg.com/vi/{item.video_id}/hqdefault.jpg"
    return None


def _parse_feed(payload: object, source_path: Path) -> ContentFeed:
    root = _mapping(payload, "feed")
    report_date = _date(root.get("report_date"), "report_date")
    generated = _timestamp(root.get("generated_at"), "generated_at")
    raw_items = _list(root.get("items"), "items")
    items = tuple(_parse_item(raw, generated) for raw in raw_items)
    ids = [item.content_id for item in items]
    urls = [item.source_url for item in items]
    if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
        raise ContentFeedError("The content feed contains duplicate IDs or URLs.")
    counts = _mapping(root.get("counts"), "counts")
    expected = {
        kind: sum(item.content_type == kind for item in items)
        for kind in ("news", "report", "video")
    }
    if any(counts.get(kind) != value for kind, value in expected.items()):
        raise ContentFeedError("Content feed counts do not match its items.")
    sources = tuple(
        _mapping(item, "source status")
        for item in _list(root.get("sources"), "sources")
    )
    return ContentFeed(
        report_date=report_date,
        generated_at=generated,
        counts=expected,
        items=items,
        sources=sources,
        source_path=source_path,
    )


def _parse_item(value: object, generated: datetime) -> ContentRecord:
    item = _mapping(value, "content item")
    content_type = _choice(
        item.get("content_type"),
        "content_type",
        {"news", "report", "video"},
    )
    source_url = _https(item.get("source_url"), "source_url")
    published = _timestamp(item.get("published_at"), "published_at")
    collected = _timestamp(item.get("collected_at"), "collected_at")
    if published > collected or collected > generated:
        raise ContentFeedError(
            "Content publication time is later than collection or feed generation."
        )
    document_url = _optional_https(item.get("document_url"), "document_url")
    video_id = _optional_text(item.get("video_id"))
    if content_type == "report" and document_url is None:
        raise ContentFeedError("Report content is missing document_url.")
    if content_type == "video" and video_id is None:
        raise ContentFeedError("Video content is missing video_id.")
    return ContentRecord(
        content_id=_text(item.get("content_id"), "content_id"),
        content_type=content_type,
        title=_text(item.get("title"), "title"),
        source_name=_text(item.get("source_name"), "source_name"),
        source_url=source_url,
        published_at=published,
        summary=_text(item.get("summary"), "summary"),
        language=_text(item.get("language"), "language"),
        region=_text(item.get("region"), "region"),
        brands=_strings(item.get("brands"), "brands"),
        vehicles=_strings(item.get("vehicles"), "vehicles"),
        topics=_strings(item.get("topics"), "topics"),
        impact_level=_choice(
            item.get("impact_level"), "impact_level", {"low", "medium", "high"}
        ),
        thumbnail_url=_optional_thumbnail(item.get("thumbnail_url")),
        document_url=document_url,
        video_id=video_id,
        collected_at=collected,
        evidence_status=_text(item.get("evidence_status"), "evidence_status"),
        ai_summary=_optional_text(item.get("ai_summary")),
        summary_mode=_text(item.get("summary_mode"), "summary_mode"),
    )


def _market_validation(vehicle: VehicleIntelligence) -> MarketValidation:
    return MarketValidation(
        vehicle_name=f"{vehicle.brand} {vehicle.model}",
        active_listing_count=vehicle.metrics.active_listing_count,
        price_change_7d_pct=vehicle.metrics.price_change_7d_pct,
        inventory_change_7d_count=vehicle.metrics.inventory_change_7d_count,
        opportunity_score=vehicle.opportunity_score.score,
    )


def _resolve(path: str | Path | None) -> Path:
    candidate = (
        Path(path).expanduser()
        if path is not None
        else get_dashboard_data_paths().content_feed
    )
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[2] / candidate
    return candidate.resolve(strict=False)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContentFeedError(f"{field} must be a JSON object.")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ContentFeedError(f"{field} must be a JSON array.")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentFeedError(f"{field} must be non-empty text.")
    return " ".join(value.split())


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value, "optional text")


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContentFeedError(f"{field} must be a JSON array.")
    return tuple(_text(item, field) for item in value)


def _date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError as exc:
        raise ContentFeedError(f"{field} must use YYYY-MM-DD.") from exc


def _timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContentFeedError(f"{field} must use ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise ContentFeedError(f"{field} must include a time zone.")
    return parsed.astimezone(UTC)


def _https(value: object, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ContentFeedError(f"{field} must be an HTTPS URL.")
    return text


def _optional_https(value: object, field: str) -> str | None:
    return None if value is None else _https(value, field)


def _optional_thumbnail(value: object) -> str | None:
    """Ignore malformed optional image metadata instead of rejecting the feed."""

    if value is None:
        return None
    try:
        return _https(value, "thumbnail_url")
    except ContentFeedError:
        return None


def _choice(value: object, field: str, allowed: set[str]) -> str:
    text = _text(value, field)
    if text not in allowed:
        raise ContentFeedError(f"{field} is not an allowed value.")
    return text


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())
