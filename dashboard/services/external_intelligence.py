"""Read-only external-intelligence adapters for the Dashboard and AI agent."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import (
    CompositeExternalIntelligenceProvider,
    ExternalIntelligenceProvider,
    ExternalQuery,
)
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveExternalProvider,
    build_live_providers,
    collect_live_external_intelligence,
)
from services.content_feed import ContentFeed, ContentRecord, load_content_feed
from services.runtime import demo_mode_enabled

LIVE_EXTERNAL_ENV = "LIVE_EXTERNAL_INTELLIGENCE"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_MINIMUM_AI_RELIABILITY = 70.0


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
