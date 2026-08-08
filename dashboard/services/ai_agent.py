"""Read-only evidence retrieval for the integrated automotive AI agent."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from ai.intelligence.agent import AutomotiveIntelligenceAgent
from ai.intelligence.api_providers import ClaudeProvider, GeminiProvider, OpenAIProvider
from ai.intelligence.models import (
    AgentAnswer,
    AgentEvidence,
    AlertEvidence,
    ExternalEvidence,
    VehicleEvidence,
)
from ai.intelligence.providers import (
    AgentLLMProvider,
    ExternalIntelligenceProvider,
    ExternalQuery,
    IntelligenceProviderError,
    UnavailableConfiguredLLMProvider,
)
from ai.intelligence.retrieval import classify_question, mentioned_vehicle_keys
from services.content_feed import ContentFeedError
from services.database import load_vehicle_analysis
from services.external_intelligence import build_default_external_provider
from services.intelligence import (
    DailyMarketIntelligence,
    VehicleIntelligence,
    vehicle_key,
)
from services.market_alerts import (
    MarketAlert,
    MarketAlertReport,
    load_market_alert_report,
)
from services.peer_benchmarking import PeerBenchmarkReport, load_peer_benchmarks

AI_PROVIDER_ENV = "AI_PROVIDER"


def answer_question(
    question: str,
    report: DailyMarketIntelligence | None,
    *,
    selected_vehicle_key: str | None = None,
    selected_alert: MarketAlert | None = None,
    external_provider: ExternalIntelligenceProvider | None = None,
    llm_provider: AgentLLMProvider | None = None,
) -> AgentAnswer:
    """Retrieve current evidence and answer without writing data or artifacts."""

    evidence = retrieve_evidence(
        question,
        report,
        selected_vehicle_key=selected_vehicle_key,
        selected_alert=selected_alert,
        external_provider=external_provider,
    )
    provider = llm_provider if llm_provider is not None else _configured_llm_provider()
    return AutomotiveIntelligenceAgent(provider).answer(evidence)


def retrieve_evidence(
    question: str,
    report: DailyMarketIntelligence | None,
    *,
    selected_vehicle_key: str | None = None,
    selected_alert: MarketAlert | None = None,
    external_provider: ExternalIntelligenceProvider | None = None,
) -> AgentEvidence:
    """Compose Analytics, Alerts, Peer, SQLite history, and external evidence."""

    cleaned_question = " ".join(question.split())
    intent = classify_question(cleaned_question)
    if report is None or not report.vehicles:
        gaps = ["Current Analytics data is unavailable."]
        try:
            provider = external_provider or build_default_external_provider()
            external = _trusted_external(
                provider.search(ExternalQuery(query=cleaned_question))
            )
        except (
            ContentFeedError,
            IntelligenceProviderError,
            OSError,
            ValueError,
        ) as exc:
            external = ()
            gaps.append(f"External intelligence unavailable: {exc}")
        if not external:
            gaps.append("External Intelligence: insufficient_data")
        return AgentEvidence(
            question=cleaned_question,
            intent=intent,
            analytics_date=None,
            external=external,
            external_status="available" if external else "insufficient_data",
            data_gaps=tuple(gaps),
        )

    gaps: list[str] = []
    alert_report = _load_alerts(report, gaps)
    peer_report = _load_peers(report, gaps)
    selected = _select_vehicles(
        report,
        intent=intent,
        question=cleaned_question,
        selected_vehicle_key=selected_vehicle_key,
        alert_report=alert_report,
    )
    vehicle_evidence = tuple(
        _vehicle_evidence(item, report, peer_report, gaps) for item in selected
    )
    selected_keys = {item.vehicle_key for item in vehicle_evidence}
    alerts = _select_alerts(alert_report, selected_keys, selected_alert)

    try:
        provider = external_provider or build_default_external_provider()
        external = _trusted_external(
            provider.search(
                ExternalQuery(
                    query=cleaned_question,
                    brands=tuple(dict.fromkeys(item.brand for item in selected)),
                    vehicles=tuple(item.vehicle_key for item in vehicle_evidence),
                    topics=_intent_topics(intent),
                )
            )
        )
    except (ContentFeedError, IntelligenceProviderError, OSError, ValueError) as exc:
        external = ()
        gaps.append(f"External intelligence unavailable: {exc}")
    if not external:
        gaps.append("External Intelligence: insufficient_data")

    return AgentEvidence(
        question=cleaned_question,
        intent=intent,
        analytics_date=report.report_date.isoformat(),
        vehicles=vehicle_evidence,
        alerts=alerts,
        external=external,
        external_status="available" if external else "insufficient_data",
        data_gaps=tuple(dict.fromkeys(gaps)),
    )


def _configured_llm_provider() -> AgentLLMProvider | None:
    name = os.getenv(AI_PROVIDER_ENV, "local").strip().casefold()
    if name in {"", "local", "local_rules", "none"}:
        return None
    if name == "openai":
        return OpenAIProvider()
    if name in {"claude", "anthropic"}:
        return ClaudeProvider()
    if name in {"gemini", "google"}:
        return GeminiProvider()
    return UnavailableConfiguredLLMProvider(name)


def _load_alerts(
    report: DailyMarketIntelligence,
    gaps: list[str],
) -> MarketAlertReport | None:
    try:
        return load_market_alert_report(report)
    except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
        gaps.append(f"Market Alerts unavailable: {exc}")
        return None


def _load_peers(
    report: DailyMarketIntelligence,
    gaps: list[str],
) -> PeerBenchmarkReport | None:
    try:
        return load_peer_benchmarks(report)
    except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
        gaps.append(f"Peer Benchmark unavailable: {exc}")
        return None


def _select_vehicles(
    report: DailyMarketIntelligence,
    *,
    intent: str,
    question: str,
    selected_vehicle_key: str | None,
    alert_report: MarketAlertReport | None,
) -> tuple[VehicleIntelligence, ...]:
    by_key = {vehicle_key(item.brand, item.model): item for item in report.vehicles}
    if selected_vehicle_key in by_key:
        return (by_key[selected_vehicle_key],)
    mentions = mentioned_vehicle_keys(question, tuple(by_key))
    if mentions:
        return tuple(by_key[key] for key in mentions[:2])
    if intent == "highest_opportunity":
        return tuple(
            sorted(
                report.vehicles,
                key=lambda item: item.opportunity_score.score,
                reverse=True,
            )[:5]
        )
    if intent in {"market_risk", "alert_explanation"} and alert_report is not None:
        risk_keys = tuple(
            dict.fromkeys(
                item.vehicle_key
                for item in alert_report.alerts
                if item.level in {"Critical", "Warning"}
            )
        )
        if risk_keys:
            return tuple(by_key[key] for key in risk_keys[:5] if key in by_key)
    if intent == "daily_brief":
        return _daily_brief_vehicles(report)
    return tuple(
        sorted(
            report.vehicles,
            key=lambda item: item.opportunity_score.score,
            reverse=True,
        )[:3]
    )


def _daily_brief_vehicles(
    report: DailyMarketIntelligence,
) -> tuple[VehicleIntelligence, ...]:
    ranked = sorted(
        report.vehicles,
        key=lambda item: (
            abs(item.metrics.price_change_7d_pct or 0)
            + abs(item.metrics.inventory_change_7d_pct or 0),
            item.opportunity_score.score,
        ),
        reverse=True,
    )
    opportunity_leader = max(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
    )
    selected: list[VehicleIntelligence] = []
    seen: set[str] = set()
    for item in (opportunity_leader, *ranked[:4]):
        key = vehicle_key(item.brand, item.model)
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return tuple(selected)


def _vehicle_evidence(
    vehicle: VehicleIntelligence,
    report: DailyMarketIntelligence,
    peer_report: PeerBenchmarkReport | None,
    gaps: list[str],
) -> VehicleEvidence:
    key = vehicle_key(vehicle.brand, vehicle.model)
    scores = report.quantitative_by_vehicle[key]
    peer = peer_report.by_vehicle.get(key) if peer_report is not None else None
    try:
        snapshot = load_vehicle_analysis(vehicle.brand, vehicle.model)
    except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
        gaps.append(f"SQLite history unavailable for {key}: {exc}")
        price_history: tuple[tuple[str, float | None], ...] = ()
        inventory_history: tuple[tuple[str, int], ...] = ()
    else:
        price_history = tuple(
            (point.observed_date, _float(point.average_price_eur))
            for point in snapshot.trend
        )
        inventory_history = tuple(
            (point.observed_date, point.observed_active_inventory)
            for point in snapshot.trend
        )
    peer_gaps = ()
    peer_gap_units = ()
    if peer is not None:
        peer_gaps = tuple(
            (name, metric.gap) for name, metric in sorted(peer.metrics.items())
        )
        peer_gap_units = tuple(
            (name, metric.gap_unit) for name, metric in sorted(peer.metrics.items())
        )
    return VehicleEvidence(
        vehicle_key=key,
        brand=vehicle.brand,
        model=vehicle.model,
        active_listing_count=vehicle.metrics.active_listing_count,
        average_asking_price_eur=vehicle.metrics.average_price_eur,
        price_change_7d_pct=vehicle.metrics.price_change_7d_pct,
        price_change_30d_pct=vehicle.metrics.price_change_30d_pct,
        inventory_change_7d_count=vehicle.metrics.inventory_change_7d_count,
        inventory_change_7d_pct=vehicle.metrics.inventory_change_7d_pct,
        new_listings_count_7d=vehicle.metrics.new_listings_count_7d,
        opportunity_score=vehicle.opportunity_score.score,
        price_pressure_index=scores.price_pressure.score,
        inventory_pressure_index=scores.inventory_pressure.score,
        market_momentum_score=scores.market_momentum.score,
        market_momentum_label=scores.market_momentum.label or "insufficient_data",
        peer_status=peer.status if peer is not None else "insufficient_data",
        peer_match_level=peer.match_level if peer is not None else None,
        peer_match_basis=peer.match_basis if peer is not None else (),
        peer_sample_size=peer.sample_size if peer is not None else 0,
        peer_rank=peer.peer_rank if peer is not None else None,
        peer_percentile=peer.peer_percentile if peer is not None else None,
        peer_gaps=peer_gaps,
        price_history=price_history,
        inventory_history=inventory_history,
        peer_gap_units=peer_gap_units,
    )


def _select_alerts(
    report: MarketAlertReport | None,
    vehicle_keys: set[str],
    selected_alert: MarketAlert | None,
) -> tuple[AlertEvidence, ...]:
    alerts: Iterable[MarketAlert]
    if selected_alert is not None:
        alerts = (selected_alert,)
    elif report is None:
        alerts = ()
    else:
        alerts = (
            item
            for item in report.alerts
            if item.vehicle_key in vehicle_keys
            and (item.level in {"Critical", "Warning"} or item.status == "available")
        )
    return tuple(
        AlertEvidence(
            alert_type=item.alert_type,
            level=item.level,
            status=item.status,
            vehicle_key=item.vehicle_key,
            trigger_reason=item.trigger_reason,
            related_metrics=tuple(sorted(item.related_metrics.items())),
            timestamp=item.timestamp.isoformat(),
        )
        for item in alerts
    )


def _intent_topics(intent: str) -> tuple[str, ...]:
    if intent in {"vehicle_pressure", "alert_explanation"}:
        return ("pricing", "inventory")
    if intent == "market_risk":
        return ("risk", "market")
    if intent == "highest_opportunity":
        return ("market", "strategy")
    return ()


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _trusted_external(
    evidence: tuple[ExternalEvidence, ...],
) -> tuple[ExternalEvidence, ...]:
    """Exclude low-reliability, unverified, or future external provider data."""

    now = datetime.now(UTC)
    trusted = []
    for item in evidence:
        try:
            published = datetime.fromisoformat(
                item.published_date.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        if (
            item.reliability < 70
            or item.evidence_type.casefold() == "unverified"
            or published.astimezone(UTC) > now
        ):
            continue
        trusted.append(item)
    return tuple(trusted)
