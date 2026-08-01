"""Transparent strategic analysis over Analytics, AI, and external evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ai.models import DailyMarketIntelligence
from strategic.ai_input import AIReportEvidence
from strategic.external import (
    ExternalIntelligenceBundle,
    ExternalSignal,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
)

_LABELED_BULLET_PATTERN = re.compile(
    r"^-\s+\*\*(?P<label>[^*]+):\*\*\s*(?P<body>.+?)\s*$",
    re.MULTILINE,
)


class EvidenceLevel(StrEnum):
    """Disclosure level for one strategic finding."""

    ANALYTICS_ONLY = "analytics_only"
    AI_SYNTHESIS = "ai_synthesis"
    EXTERNAL_SOURCE = "external_source"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class StrategicFinding:
    """One explainable opportunity or competitive-risk finding."""

    headline: str
    analysis: str
    evidence: tuple[str, ...]
    evidence_level: EvidenceLevel


@dataclass(frozen=True)
class StrategicRecommendation:
    """One management action with rationale and an explicit decision gate."""

    priority: int
    action: str
    rationale: str
    decision_gate: str


@dataclass(frozen=True)
class StrategicAnalysis:
    """Complete strategic output ready for management reporting."""

    report_date: str
    opportunities: tuple[StrategicFinding, ...]
    competitive_risks: tuple[StrategicFinding, ...]
    recommendations: tuple[StrategicRecommendation, ...]
    external_intelligence: ExternalIntelligenceBundle
    ai_generation_mode: str
    ai_evidence_sha256: str | None
    data_gaps: tuple[str, ...]


def build_strategic_analysis(
    analytics: DailyMarketIntelligence,
    ai_report: AIReportEvidence,
    external: ExternalIntelligenceBundle,
) -> StrategicAnalysis:
    """Build management findings without inferring unavailable market facts."""

    if analytics.report_date != ai_report.report_date:
        raise ValueError(
            "Analytics and AI report dates do not match: "
            f"analytics={analytics.report_date} ai={ai_report.report_date}"
        )
    opportunities = _market_opportunities(analytics, ai_report, external)
    risks = _competitive_risks(analytics, ai_report, external)
    data_gaps = _data_gaps(analytics, external)
    recommendations = _recommendations(analytics, external, data_gaps)
    return StrategicAnalysis(
        report_date=analytics.report_date.isoformat(),
        opportunities=opportunities,
        competitive_risks=risks,
        recommendations=recommendations,
        external_intelligence=external,
        ai_generation_mode=ai_report.generation_mode,
        ai_evidence_sha256=ai_report.evidence_sha256,
        data_gaps=data_gaps,
    )


def _market_opportunities(
    analytics: DailyMarketIntelligence,
    ai_report: AIReportEvidence,
    external: ExternalIntelligenceBundle,
) -> tuple[StrategicFinding, ...]:
    findings: list[StrategicFinding] = []
    ranked = sorted(
        analytics.vehicles,
        key=lambda item: (
            -item.opportunity_score.score,
            item.brand.casefold(),
            item.model.casefold(),
        ),
    )
    for vehicle in ranked[:3]:
        metrics = vehicle.metrics
        entity = f"{vehicle.brand} {vehicle.model}".casefold()
        kba_signal = next(
            (
                signal
                for signal in external.kba.signals
                if (signal.entity or "").casefold() == entity
                and signal.metric_name == "official_new_registrations"
            ),
            None,
        )
        evidence = [
            f"Opportunity score: {vehicle.opportunity_score.score:.2f}/100",
            f"Active listing inventory: {metrics.active_listing_count:,}",
            f"Seven-day new listings: {metrics.new_listings_count_7d:,}",
            "Average asking price: " + _price_text(metrics.average_price_eur),
        ]
        if kba_signal is not None:
            evidence.extend(
                (
                    "Official KBA new registrations: "
                    f"{int(kba_signal.metric_value or 0):,}",
                    f"KBA source URL: {kba_signal.source_url}",
                )
            )
        findings.append(
            StrategicFinding(
                headline=f"Research priority: {vehicle.brand} {vehicle.model}",
                analysis=(
                    "The project opportunity model places this vehicle in the top "
                    "current research tier. This is a marketplace research signal, "
                    "not an investment recommendation or demand forecast."
                ),
                evidence=tuple(evidence),
                evidence_level=(
                    EvidenceLevel.EXTERNAL_SOURCE
                    if kba_signal is not None
                    else EvidenceLevel.ANALYTICS_ONLY
                ),
            )
        )
    if not ranked:
        findings.append(
            StrategicFinding(
                headline="No vehicle opportunity can be ranked",
                analysis=(
                    "The Analytics input contains no vehicle observations; the "
                    "strategic layer does not impute opportunity signals."
                ),
                evidence=("Vehicle observations: 0",),
                evidence_level=EvidenceLevel.INSUFFICIENT_DATA,
            )
        )

    ai_opportunity = _labeled_bullets(
        ai_report.sections["Risk and opportunity summary"],
        labels={"opportunity", "activity signal"},
    )
    if ai_opportunity:
        findings.append(
            StrategicFinding(
                headline="AI report opportunity context",
                analysis=(
                    "The upstream AI report contributes the following grounded "
                    "summary; it remains subject to the same Analytics limitations."
                ),
                evidence=ai_opportunity,
                evidence_level=EvidenceLevel.AI_SYNTHESIS,
            )
        )
    findings.extend(_external_findings(external, StrategicImplication.OPPORTUNITY))
    return tuple(findings)


def _competitive_risks(
    analytics: DailyMarketIntelligence,
    ai_report: AIReportEvidence,
    external: ExternalIntelligenceBundle,
) -> tuple[StrategicFinding, ...]:
    findings: list[StrategicFinding] = []
    vehicle_count = len(analytics.vehicles)
    coverage_7d = sum(
        vehicle.metrics.price_change_7d_pct is not None
        for vehicle in analytics.vehicles
    )
    coverage_30d = sum(
        vehicle.metrics.price_change_30d_pct is not None
        for vehicle in analytics.vehicles
    )
    if vehicle_count:
        findings.append(
            StrategicFinding(
                headline="Price-trend coverage limits directional conclusions",
                analysis=(
                    "Short and medium-window asking-price evidence is incomplete. "
                    "Competitive pricing actions should wait for broader history."
                ),
                evidence=(
                    f"Seven-day coverage: {coverage_7d}/{vehicle_count} vehicles",
                    f"Thirty-day coverage: {coverage_30d}/{vehicle_count} vehicles",
                ),
                evidence_level=EvidenceLevel.ANALYTICS_ONLY,
            )
        )

    if analytics.brands and analytics.active_inventory_count:
        leader = min(
            analytics.brands,
            key=lambda item: (
                item.metrics.active_inventory_rank,
                item.brand.casefold(),
            ),
        )
        share = (
            leader.metrics.active_inventory_count
            / analytics.active_inventory_count
            * 100
        )
        findings.append(
            StrategicFinding(
                headline=f"Tracked inventory concentration: {leader.brand}",
                analysis=(
                    "The leading brand accounts for a material share of observed "
                    "active inventory. This measures listing presence, not sales or "
                    "registered-market share."
                ),
                evidence=(
                    f"Inventory rank: #{leader.metrics.active_inventory_rank}",
                    f"Active listings: {leader.metrics.active_inventory_count:,}",
                    f"Share of tracked active inventory: {share:.2f}%",
                ),
                evidence_level=EvidenceLevel.ANALYTICS_ONLY,
            )
        )

    ai_risks = _labeled_bullets(
        ai_report.sections["Risk and opportunity summary"],
        labels={"trend-data risk", "measurement risk"},
    )
    if ai_risks:
        findings.append(
            StrategicFinding(
                headline="AI report risk synthesis",
                analysis="The upstream AI report identifies these evidence limits.",
                evidence=ai_risks,
                evidence_level=EvidenceLevel.AI_SYNTHESIS,
            )
        )
    findings.extend(_external_findings(external, StrategicImplication.RISK))
    return tuple(findings)


def _external_findings(
    external: ExternalIntelligenceBundle,
    implication: StrategicImplication,
) -> list[StrategicFinding]:
    findings = []
    for snapshot in external.snapshots:
        for signal in snapshot.signals:
            if signal.implication is implication:
                findings.append(_external_finding(snapshot.source_type, signal))
    return findings


def _external_finding(
    source_type: ExternalSourceType,
    signal: ExternalSignal,
) -> StrategicFinding:
    metric = ""
    if signal.metric_name and signal.metric_value is not None:
        unit = f" {signal.unit}" if signal.unit else ""
        metric = f"{signal.metric_name}: {signal.metric_value}{unit}"
    evidence = [f"Source type: {source_type}", f"Source URL: {signal.source_url}"]
    if metric:
        evidence.append(metric)
    return StrategicFinding(
        headline=signal.title,
        analysis=signal.summary,
        evidence=tuple(evidence),
        evidence_level=EvidenceLevel.EXTERNAL_SOURCE,
    )


def _data_gaps(
    analytics: DailyMarketIntelligence,
    external: ExternalIntelligenceBundle,
) -> tuple[str, ...]:
    gaps = []
    source_labels = {
        ExternalSourceType.KBA_REGISTRATIONS: "KBA registration data",
        ExternalSourceType.NEWS: "automotive news intelligence",
        ExternalSourceType.BRAND_NEWS: "official brand-news intelligence",
        ExternalSourceType.MARKET_DATA: "external market data",
    }
    for snapshot in external.snapshots:
        if snapshot.status is not ExternalSourceStatus.AVAILABLE:
            gaps.append(
                f"{source_labels[snapshot.source_type]} is {snapshot.status.value}."
            )
    if analytics.vehicles:
        coverage_30d = sum(
            vehicle.metrics.price_change_30d_pct is not None
            for vehicle in analytics.vehicles
        )
        if coverage_30d < len(analytics.vehicles):
            gaps.append(
                "Thirty-day price history is incomplete: "
                f"{coverage_30d}/{len(analytics.vehicles)} vehicles covered."
            )
    else:
        gaps.append("Analytics contains no vehicle observations.")
    return tuple(gaps)


def _recommendations(
    analytics: DailyMarketIntelligence,
    external: ExternalIntelligenceBundle,
    data_gaps: tuple[str, ...],
) -> tuple[StrategicRecommendation, ...]:
    recommendations: list[StrategicRecommendation] = []
    ranked = sorted(
        analytics.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    if ranked:
        top = ranked[0]
        recommendations.append(
            StrategicRecommendation(
                priority=1,
                action=f"Prioritize validation of {top.brand} {top.model}.",
                rationale=(
                    f"It has the highest current project opportunity score "
                    f"({top.opportunity_score.score:.2f}/100)."
                ),
                decision_gate=(
                    "Do not treat the score as demand until registration or other "
                    "independent market evidence corroborates the signal."
                ),
            )
        )
    else:
        recommendations.append(
            StrategicRecommendation(
                priority=1,
                action="Restore Analytics vehicle coverage before prioritization.",
                rationale="No vehicle observations are available.",
                decision_gate="No vehicle ranking may be issued from empty input.",
            )
        )

    kba = external.kba
    if kba.status is not ExternalSourceStatus.AVAILABLE:
        recommendations.append(
            StrategicRecommendation(
                priority=2,
                action="Connect a governed KBA registration provider.",
                rationale=(
                    "Official registration evidence is required to test whether "
                    "listing activity aligns with registered-market movement."
                ),
                decision_gate=(
                    "Preserve the distinction between registrations, listings, and "
                    "transactions."
                ),
            )
        )
    if any("Thirty-day price history" in gap for gap in data_gaps):
        recommendations.append(
            StrategicRecommendation(
                priority=3,
                action="Extend the observation window before pricing intervention.",
                rationale="Thirty-day price-trend coverage is incomplete.",
                decision_gate=(
                    "Require a valid historical baseline and review composition "
                    "effects before declaring a price trend."
                ),
            )
        )
    missing_context = tuple(
        snapshot.source_type.value
        for snapshot in (
            external.news,
            external.brand_news,
            external.market_data,
        )
        if snapshot.status is not ExternalSourceStatus.AVAILABLE
    )
    if missing_context:
        recommendations.append(
            StrategicRecommendation(
                priority=4,
                action="Add attributed news and external-market context providers.",
                rationale=(
                    "Current recommendations cannot test policy, launch, incentive, "
                    "or broader market context."
                ),
                decision_gate=(
                    "Accept only source-attributed signals with dates and URLs; "
                    "provider failure must not be converted into facts."
                ),
            )
        )
    return tuple(recommendations)


def _labeled_bullets(markdown: str, *, labels: set[str]) -> tuple[str, ...]:
    return tuple(
        f"{match.group('label').strip()}: {match.group('body').strip()}"
        for match in _LABELED_BULLET_PATTERN.finditer(markdown)
        if match.group("label").strip().casefold() in labels
    )


def _price_text(value: float | None) -> str:
    return "unavailable" if value is None else f"EUR {value:,.0f}"
