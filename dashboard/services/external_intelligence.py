"""Read-only external-intelligence adapters for the Dashboard and AI agent."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import (
    CompositeExternalIntelligenceProvider,
    ExternalIntelligenceProvider,
    ExternalQuery,
)
from external_intelligence.content_models import canonical_url
from external_intelligence.live_config import load_live_config
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveExternalProvider,
    build_live_providers,
    build_live_providers_from_config,
    collect_live_external_intelligence,
)
from external_intelligence.live_refresh import (
    LiveCollectionSnapshotStore,
    LiveRefreshCoordinator,
    LiveRefreshState,
)
from external_intelligence.vehicle_catalog import MonitoredVehicle
from services.content_feed import ContentFeed, ContentRecord, load_content_feed
from services.runtime import demo_mode_enabled

LIVE_EXTERNAL_ENV = "LIVE_EXTERNAL_INTELLIGENCE"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_MINIMUM_AI_RELIABILITY = 70.0
_LIVE_REFRESH_INTERVAL_SECONDS = 900.0
_LIVE_REFRESH_COORDINATOR: LiveRefreshCoordinator | None = None
_LIVE_REFRESH_COORDINATOR_LOCK = threading.Lock()


@dataclass(frozen=True)
class HubIntelligenceSections:
    """Evidence-backed content groups shown in the existing content hub."""

    external_news: tuple[ContentRecord, ...]
    brand_updates: tuple[ContentRecord, ...]
    industry_signals: tuple[ContentRecord, ...]


@dataclass(frozen=True)
class LiveHubSections:
    """Four source-backed live views shown in the existing content hub."""

    latest_automotive_news: tuple[ExternalEvidence, ...]
    policy_updates: tuple[ExternalEvidence, ...]
    brand_intelligence: tuple[ExternalEvidence, ...]
    industry_signals: tuple[ExternalEvidence, ...]


@dataclass(frozen=True)
class VehicleContentCoverage:
    """Evidence-backed coverage state for one monitored vehicle."""

    vehicle: MonitoredVehicle
    item_count: int
    latest_published_at: datetime | None

    @property
    def status(self) -> str:
        """Return the explicit coverage state without filling absent evidence."""

        return "covered" if self.item_count else "insufficient_data"


@dataclass(frozen=True)
class ContentCoverageSummary:
    """Current source and monitored-entity coverage for the content hub."""

    brands_covered: tuple[str, ...]
    vehicles_covered: tuple[str, ...]
    active_sources: tuple[str, ...]
    latest_update: datetime | None
    vehicles: tuple[VehicleContentCoverage, ...]


class ContentFeedExternalIntelligenceProvider:
    """Search validated Content Feed metadata without network access or writes."""

    name = "project_germania_content_feed"
    capabilities = frozenset(
        {"news", "search", "official_brand_news", "industry_report"}
    )

    def __init__(
        self,
        loader: Callable[[], ContentFeed] = load_content_feed,
    ) -> None:
        self._loader = loader

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Return relevant source metadata mapped to the unified evidence model."""

        feed = self._loader()
        scored: list[tuple[int, ContentRecord]] = []
        query_terms = {
            term for term in _normalize(query.query).split() if len(term) >= 3
        }
        brand_terms = {_normalize(value) for value in query.brands}
        vehicle_terms = {_normalize(value) for value in query.vehicles}
        topic_terms = {_normalize(value) for value in query.topics}
        for item in feed.items:
            score = _content_relevance(
                item,
                query_terms=query_terms,
                brands=brand_terms,
                vehicles=vehicle_terms,
                topics=topic_terms,
            )
            if score > 0 or not (
                query_terms or brand_terms or vehicle_terms or topic_terms
            ):
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].published_at), reverse=True)
        evidence = tuple(_to_external_evidence(item) for _, item in scored)
        return tuple(
            item for item in evidence if item.reliability >= _MINIMUM_AI_RELIABILITY
        )[: query.limit]


def live_external_enabled(value: str | bool | None = None) -> bool:
    """Return whether Production should query live sources; Demo never does."""

    if demo_mode_enabled():
        return False
    if isinstance(value, bool):
        return value
    raw = os.getenv(LIVE_EXTERNAL_ENV, "true") if value is None else value
    normalized = str(raw).strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{LIVE_EXTERNAL_ENV} must be one of: true, false, 1, 0, yes, no, on, off."
    )


def build_default_external_provider(
    *,
    live_providers: tuple[LiveExternalProvider, ...] | None = None,
) -> ExternalIntelligenceProvider:
    """Combine the validated artifact with live providers in Production only."""

    static_provider = ContentFeedExternalIntelligenceProvider()
    if not live_external_enabled():
        return static_provider
    configured = (
        live_providers if live_providers is not None else build_live_providers()
    )
    return CompositeExternalIntelligenceProvider((static_provider, *configured))


def load_live_external_collection(
    query: ExternalQuery,
    *,
    providers: tuple[LiveExternalProvider, ...] | None = None,
) -> LiveExternalCollection:
    """Fetch current live evidence without changing generated report artifacts."""

    if not live_external_enabled():
        raise ValueError("Live external intelligence is disabled in this runtime mode.")
    configured = providers if providers is not None else build_live_providers()
    return collect_live_external_intelligence(configured, query)


def request_live_external_refresh(
    query: ExternalQuery,
    *,
    force: bool = False,
) -> LiveRefreshState:
    """Return cached evidence immediately and refresh it in the background."""

    coordinator = _live_refresh_coordinator()
    coordinator.request_refresh(query, force=force)
    return coordinator.state()


def _live_refresh_coordinator() -> LiveRefreshCoordinator:
    """Build one process-wide coordinator shared by all Streamlit reruns."""

    global _LIVE_REFRESH_COORDINATOR
    if _LIVE_REFRESH_COORDINATOR is not None:
        return _LIVE_REFRESH_COORDINATOR
    with _LIVE_REFRESH_COORDINATOR_LOCK:
        if _LIVE_REFRESH_COORDINATOR is None:
            config = load_live_config()
            store = LiveCollectionSnapshotStore(
                config.cache_directory / "latest_collection.json"
            )

            def load(query: ExternalQuery) -> LiveExternalCollection:
                return collect_live_external_intelligence(
                    build_live_providers_from_config(config),
                    query,
                    provider_timeout_seconds=max(
                        15.0,
                        config.http.timeout_seconds * 2.5,
                    ),
                )

            _LIVE_REFRESH_COORDINATOR = LiveRefreshCoordinator(
                loader=load,
                store=store,
                refresh_interval_seconds=_LIVE_REFRESH_INTERVAL_SECONDS,
            )
    return _LIVE_REFRESH_COORDINATOR


def build_hub_intelligence_sections(
    items: tuple[ContentRecord, ...],
) -> HubIntelligenceSections:
    """Group current source items without inferring unverified facts or causality."""

    return HubIntelligenceSections(
        external_news=tuple(item for item in items if item.content_type == "news"),
        brand_updates=tuple(
            item for item in items if item.content_type == "news" and bool(item.brands)
        ),
        industry_signals=tuple(
            item
            for item in items
            if item.content_type == "report"
            or (item.content_type == "news" and not item.brands and bool(item.topics))
        ),
    )


def build_live_hub_sections(
    items: tuple[ContentRecord, ...],
    live_evidence: tuple[ExternalEvidence, ...] = (),
) -> LiveHubSections:
    """Merge validated artifacts and live evidence into four non-causal views."""

    static_evidence = tuple(
        evidence
        for item in items
        if item.content_type != "video"
        and (evidence := _to_external_evidence(item)).reliability
        >= _MINIMUM_AI_RELIABILITY
    )
    by_url: dict[str, ExternalEvidence] = {}
    for evidence in (*live_evidence, *static_evidence):
        by_url.setdefault(evidence.url, evidence)
    merged = tuple(
        sorted(
            by_url.values(),
            key=lambda item: (item.published_date, item.reliability),
            reverse=True,
        )
    )
    return LiveHubSections(
        latest_automotive_news=tuple(
            item for item in merged if item.category in {"news", "automotive_news"}
        ),
        policy_updates=tuple(
            item for item in merged if item.category == "policy_regulation"
        ),
        brand_intelligence=tuple(
            item
            for item in merged
            if item.category == "brand_intelligence"
            or (
                item.category == "news"
                and item.brand is not None
                and item.evidence_type != "unverified"
            )
        ),
        industry_signals=tuple(
            item for item in merged if item.category == "industry_report"
        ),
    )


def merge_external_content(
    items: tuple[ContentRecord, ...],
    live_evidence: tuple[ExternalEvidence, ...] = (),
) -> tuple[ContentRecord, ...]:
    """Merge validated live evidence into cards, then deduplicate and diversify."""

    candidates = [*items, *(_evidence_record(item) for item in live_evidence)]
    by_url: dict[str, ContentRecord] = {}
    for item in candidates:
        key = canonical_url(item.source_url)
        current = by_url.get(key)
        if current is None or _record_priority(item) > _record_priority(current):
            by_url[key] = item
    by_title: dict[str, ContentRecord] = {}
    for item in by_url.values():
        key = _normalize(item.title)
        current = by_title.get(key)
        if current is None or _record_priority(item) > _record_priority(current):
            by_title[key] = item
    return diversify_content(tuple(by_title.values()))


def diversify_content(
    items: tuple[ContentRecord, ...],
) -> tuple[ContentRecord, ...]:
    """Round-robin reliable content groups so one brand cannot own the first row."""

    ranked = sorted(items, key=_record_priority, reverse=True)
    output: list[ContentRecord] = []
    for reliability_band in (2, 1):
        groups: dict[str, list[ContentRecord]] = {}
        for item in ranked:
            if _reliability_band(item) != reliability_band:
                continue
            groups.setdefault(_diversity_key(item), []).append(item)
        ordered_keys = sorted(
            groups,
            key=lambda key: _record_priority(groups[key][0]),
            reverse=True,
        )
        while ordered_keys:
            next_keys: list[str] = []
            for key in ordered_keys:
                group = groups[key]
                output.append(group.pop(0))
                if group:
                    next_keys.append(key)
            ordered_keys = next_keys
    return tuple(output)


def calculate_content_coverage(
    items: tuple[ContentRecord, ...],
    monitored_vehicles: tuple[MonitoredVehicle, ...],
) -> ContentCoverageSummary:
    """Measure exact coverage against the dynamically configured monitoring set."""

    monitored_brand_names = {
        _normalize(item.brand): item.brand for item in monitored_vehicles
    }
    monitored_vehicle_names = {
        _normalize(item.display_name): item.display_name for item in monitored_vehicles
    }
    covered_brand_keys = {
        _normalize(brand)
        for item in items
        for brand in item.brands
        if _normalize(brand) in monitored_brand_names
    }
    covered_vehicle_keys = {
        _normalize(vehicle)
        for item in items
        for vehicle in item.vehicles
        if _normalize(vehicle) in monitored_vehicle_names
    }
    coverage_rows = []
    for vehicle in monitored_vehicles:
        key = _normalize(vehicle.display_name)
        matches = tuple(
            item
            for item in items
            if key in {_normalize(value) for value in item.vehicles}
        )
        coverage_rows.append(
            VehicleContentCoverage(
                vehicle=vehicle,
                item_count=len(matches),
                latest_published_at=max(
                    (item.published_at for item in matches),
                    default=None,
                ),
            )
        )
    return ContentCoverageSummary(
        brands_covered=tuple(
            sorted(monitored_brand_names[key] for key in covered_brand_keys)
        ),
        vehicles_covered=tuple(
            sorted(monitored_vehicle_names[key] for key in covered_vehicle_keys)
        ),
        active_sources=tuple(sorted({item.source_name for item in items})),
        latest_update=max((item.collected_at for item in items), default=None),
        vehicles=tuple(coverage_rows),
    )


def _content_relevance(
    item: ContentRecord,
    *,
    query_terms: set[str],
    brands: set[str],
    vehicles: set[str],
    topics: set[str],
) -> int:
    searchable = _normalize(
        " ".join((item.title, item.summary, *item.brands, *item.vehicles, *item.topics))
    )
    item_brands = {_normalize(value) for value in item.brands}
    item_vehicles = {_normalize(value) for value in item.vehicles}
    item_topics = {_normalize(value) for value in item.topics}
    return (
        sum(term in searchable for term in query_terms)
        + 4 * len(brands.intersection(item_brands))
        + 6 * len(vehicles.intersection(item_vehicles))
        + 2 * len(topics.intersection(item_topics))
    )


def _to_external_evidence(item: ContentRecord) -> ExternalEvidence:
    category = {
        "news": "news",
        "report": "industry_report",
        "video": "search",
    }[item.content_type]
    return ExternalEvidence(
        source=item.source_name,
        title=item.title,
        url=item.document_url or item.source_url,
        published_date=item.published_at.isoformat(),
        category=category,
        brand=", ".join(item.brands) or None,
        vehicle=", ".join(item.vehicles) or None,
        content_summary=item.summary,
        reliability=_content_feed_reliability(item.evidence_status),
        fetched_time=item.collected_at.isoformat(),
        evidence_type={
            "news": "validated_content_feed_news",
            "report": "validated_content_feed_report",
            "video": "validated_public_video",
        }[item.content_type],
        region=item.region,
    )


def _evidence_record(item: ExternalEvidence) -> ContentRecord:
    published = _external_timestamp(item.published_date)
    collected = _external_timestamp(item.fetched_time)
    content_type = "report" if item.category == "industry_report" else "news"
    brands = _split_entities(item.brand)
    vehicles = _split_entities(item.vehicle)
    topics = tuple(
        dict.fromkeys(
            (
                item.category.replace("_", " "),
                item.evidence_type.replace("_", " "),
            )
        )
    )
    identifier = hashlib.sha256(
        f"{content_type}\0{canonical_url(item.url)}".encode()
    ).hexdigest()[:24]
    evidence_status = (
        "stale_verified_source" if item.reliability <= 70 else "official_source"
    )
    return ContentRecord(
        content_id=identifier,
        content_type=content_type,
        title=item.title,
        source_name=item.source,
        source_url=item.url,
        published_at=published,
        summary=item.content_summary,
        language="und",
        region=item.region,
        brands=brands,
        vehicles=vehicles,
        topics=topics,
        impact_level=(
            "high" if vehicles or item.category == "policy_regulation" else "medium"
        ),
        thumbnail_url=item.image_url,
        document_url=item.url if content_type == "report" else None,
        video_id=None,
        collected_at=max(collected, published),
        evidence_status=evidence_status,
        ai_summary=item.content_summary,
        summary_mode="external_provider_metadata",
    )


def _external_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _split_entities(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(
        dict.fromkeys(part.strip() for part in value.split(",") if part.strip())
    )


def _record_priority(item: ContentRecord) -> tuple[int, datetime, int]:
    return (
        _reliability_band(item),
        item.published_at,
        1 if item.thumbnail_url else 0,
    )


def _reliability_band(item: ContentRecord) -> int:
    return 1 if "stale" in item.evidence_status.casefold() else 2


def _diversity_key(item: ContentRecord) -> str:
    if item.vehicles:
        return f"vehicle:{_normalize(item.vehicles[0])}"
    if item.brands:
        return f"brand:{_normalize(item.brands[0])}"
    category = _content_category(item)
    return f"{category}:{_normalize(item.source_name)}"


def content_category(item: ContentRecord) -> str:
    """Return the presentation channel for one source-attributed record."""

    return _content_category(item)


def _content_category(item: ContentRecord) -> str:
    topics = " ".join(item.topics).casefold()
    if any(
        term in topics for term in ("policy", "regulation", "government", "legislation")
    ):
        return "Policy"
    if item.content_type == "report" or any(
        term in topics for term in ("industry", "registration", "official public data")
    ):
        return "Industry"
    if item.vehicles:
        return "Vehicles"
    if item.brands:
        return "Brands"
    return "Industry"


def _content_feed_reliability(status: str) -> float:
    normalized = status.casefold()
    if "stale" in normalized:
        return 70.0
    if "official" in normalized:
        return 95.0
    if "verified" in normalized:
        return 85.0
    return 0.0


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())
