"""Evidence-grounded agent with an optional LLM and deterministic fallback."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ai.intelligence.models import (
    AgentAnswer,
    AgentEvidence,
    EvidenceRecord,
    VehicleEvidence,
)
from ai.intelligence.prompts import REQUIRED_HEADINGS, SYSTEM_PROMPT
from ai.intelligence.providers import (
    AgentLLMProvider,
    AgentLLMRequest,
    IntelligenceProviderError,
)

NO_EVIDENCE_MESSAGE = "insufficient_data"
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")
_PEER_GAP_LABELS = {
    "price_gap_pct": "Price Gap",
    "inventory_gap_pct": "Inventory Gap",
    "price_trend_gap_pp": "Price Trend Gap",
    "opportunity_score_gap": "Opportunity Score Gap",
    "price_pressure_gap": "Price Pressure Gap",
    "inventory_pressure_gap": "Inventory Pressure Gap",
    "market_momentum_gap": "Market Momentum Gap",
}


class AutomotiveIntelligenceAgent:
    """Generate auditable answers from retrieved evidence only."""

    def __init__(self, provider: AgentLLMProvider | None = None) -> None:
        self._provider = provider

    def answer(self, evidence: AgentEvidence) -> AgentAnswer:
        """Return a grounded answer, falling back locally when the LLM fails."""

        draft = _local_answer(evidence)
        if self._provider is None:
            return draft
        request = AgentLLMRequest(
            question=evidence.question,
            intent=evidence.intent,
            evidence_sha256=evidence.sha256(),
            evidence_json=evidence.canonical_json(),
            grounded_draft_markdown=draft.to_markdown(),
            system_prompt=SYSTEM_PROMPT,
        )
        try:
            result = self._provider.generate(request)
            if result.evidence_sha256 != request.evidence_sha256:
                raise IntelligenceProviderError("LLM evidence digest mismatch.")
            _validate_provider_markdown(result.markdown, request)
            return _parse_provider_answer(
                result.markdown,
                provider_name=self._provider.name,
                evidence_sha256=request.evidence_sha256,
                evidence_records=draft.evidence_records,
            )
        except (IntelligenceProviderError, OSError, ValueError, RuntimeError):
            return AgentAnswer(
                **{
                    **draft.__dict__,
                    "generation_mode": "local_rules_fallback",
                    "provider_name": self._provider.name,
                }
            )


def _local_answer(evidence: AgentEvidence) -> AgentAnswer:
    digest = evidence.sha256()
    if not evidence.has_evidence:
        return AgentAnswer(
            situation_summary=NO_EVIDENCE_MESSAGE,
            evidence=(NO_EVIDENCE_MESSAGE,),
            key_drivers=(NO_EVIDENCE_MESSAGE,),
            competitive_implication=NO_EVIDENCE_MESSAGE,
            recommended_monitoring_actions=(
                "Wait for a valid Analytics artifact or verified external source.",
            ),
            confidence_level="Insufficient",
            generation_mode="local_rules",
            provider_name="local_rules",
            evidence_sha256=digest,
            evidence_records=(),
        )

    vehicle_lines = tuple(_vehicle_evidence_line(item) for item in evidence.vehicles)
    alert_lines = tuple(
        f"Internal Data Evidence — {item.vehicle_key}: {item.alert_type} is "
        f"{item.level or item.status}; {item.trigger_reason}"
        for item in evidence.alerts
    )
    external_lines = tuple(
        f"External Market Signal — {item.source}: {item.title} "
        f"({item.url}; reliability: {item.reliability:.0f}/100; "
        f"type: {item.evidence_type}; region: {item.region})"
        for item in evidence.external
    )
    evidence_lines = vehicle_lines + alert_lines + external_lines
    if evidence.intent == "vehicle_comparison" and len(evidence.vehicles) >= 2:
        first, second = evidence.vehicles[:2]
        summary = (
            f"{first.vehicle_key} and {second.vehicle_key} are compared using "
            "current asking-price, listing-inventory, pressure, momentum, and "
            "peer evidence where available."
        )
        implication = _comparison_implication(first, second)
    elif evidence.intent == "highest_opportunity" and evidence.vehicles:
        leader = max(evidence.vehicles, key=lambda item: item.opportunity_score)
        summary = (
            f"{leader.vehicle_key} has the highest Vehicle Opportunity Score "
            f"within the retrieved set at {leader.opportunity_score:.2f}."
        )
        implication = (
            "The ranking is a project-model signal for prioritizing further "
            "market review; it is not an official ranking or a sales forecast."
        )
    elif evidence.intent in {"market_risk", "alert_explanation"}:
        active = [
            item for item in evidence.alerts if item.level in {"Critical", "Warning"}
        ]
        summary = (
            f"{len(active)} retrieved alert evaluations are currently Critical "
            "or Warning."
            if active
            else "No retrieved alert evaluation currently crosses a risk threshold."
        )
        implication = (
            "Threshold crossings identify vehicles for monitoring; they do not "
            "prove demand loss, realized sales, or a causal market event."
        )
    elif evidence.vehicles:
        subject = evidence.vehicles[0]
        summary = _vehicle_summary(subject)
        implication = _vehicle_implication(subject)
    else:
        summary = (
            "Verified external intelligence is available, but no current internal "
            "vehicle metric was retrieved for validation."
        )
        implication = (
            "Treat external items as monitoring context until internal market "
            "signals can confirm a vehicle-level implication."
        )

    return AgentAnswer(
        situation_summary=summary,
        evidence=evidence_lines or (NO_EVIDENCE_MESSAGE,),
        key_drivers=_drivers(evidence),
        competitive_implication=implication,
        recommended_monitoring_actions=_actions(evidence),
        confidence_level=_confidence(evidence),
        generation_mode="local_rules",
        provider_name="local_rules",
        evidence_sha256=digest,
        evidence_records=_structured_evidence(evidence),
    )


def _vehicle_evidence_line(item: VehicleEvidence) -> str:
    values = [
        f"active listings {item.active_listing_count:,}",
        f"Vehicle Opportunity Score {item.opportunity_score:.2f}",
    ]
    if item.average_asking_price_eur is not None:
        values.append(f"average asking price EUR {item.average_asking_price_eur:,.0f}")
    if item.price_change_7d_pct is not None:
        values.append(f"7-day asking-price change {item.price_change_7d_pct:+.2f}%")
    if item.inventory_change_7d_pct is not None:
        values.append(
            f"7-day listing-inventory change {item.inventory_change_7d_pct:+.2f}%"
        )
    if item.price_pressure_index is not None:
        values.append(f"Price Pressure Index {item.price_pressure_index:.2f}")
    if item.inventory_pressure_index is not None:
        values.append(f"Inventory Pressure Index {item.inventory_pressure_index:.2f}")
    if item.market_momentum_score is not None:
        values.append(
            f"Market Momentum {item.market_momentum_score:.2f} "
            f"({item.market_momentum_label})"
        )
    if item.peer_rank is not None:
        values.append(
            f"peer rank {item.peer_rank}/{item.peer_sample_size} "
            f"(percentile {item.peer_percentile:.2f})"
        )
    return f"Internal Data Evidence — {item.vehicle_key}: " + "; ".join(values)


def _vehicle_summary(item: VehicleEvidence) -> str:
    signals = []
    if item.price_pressure_index is not None:
        signals.append(f"Price Pressure {item.price_pressure_index:.2f}")
    if item.inventory_pressure_index is not None:
        signals.append(f"Inventory Pressure {item.inventory_pressure_index:.2f}")
    if item.market_momentum_score is not None:
        signals.append(
            f"Market Momentum {item.market_momentum_score:.2f} "
            f"({item.market_momentum_label})"
        )
    if not signals:
        return (
            f"{item.vehicle_key} has current listing evidence, but the requested "
            "pressure and momentum signals are incomplete."
        )
    return f"{item.vehicle_key} currently shows " + ", ".join(signals) + "."


def _vehicle_implication(item: VehicleEvidence) -> str:
    if item.market_momentum_score is None:
        return (
            "Current data supports inventory and asking-price monitoring, but not "
            "a complete competitive-position conclusion."
        )
    if item.market_momentum_score < 40:
        return (
            "Negative market momentum alongside current pressure signals warrants "
            "closer peer and asking-price monitoring; it does not establish sales loss."
        )
    if item.market_momentum_score >= 60:
        return (
            "Positive market momentum supports prioritizing the vehicle for further "
            "opportunity review, subject to peer and history confidence."
        )
    return (
        "The current signal is neutral and does not support a directional conclusion."
    )


def _comparison_implication(first: VehicleEvidence, second: VehicleEvidence) -> str:
    opportunity_gap = first.opportunity_score - second.opportunity_score
    return (
        f"The retrieved Vehicle Opportunity Score gap is {opportunity_gap:+.2f} "
        f"points for {first.vehicle_key} versus {second.vehicle_key}. Interpret "
        "that gap together with each vehicle's peer controls and data coverage."
    )


def _drivers(evidence: AgentEvidence) -> tuple[str, ...]:
    drivers: list[str] = []
    for item in evidence.vehicles[:4]:
        if item.price_change_7d_pct is not None and item.price_change_7d_pct < 0:
            drivers.append(
                f"{item.vehicle_key} asking prices decreased over 7 days while "
                "the observed direction is monitored as a pressure signal."
            )
        if (
            item.inventory_change_7d_pct is not None
            and item.inventory_change_7d_pct > 0
        ):
            drivers.append(
                f"{item.vehicle_key} listing inventory increased over 7 days; "
                "this is inventory coverage, not sales or unsold volume."
            )
        if item.peer_status == "ok" and item.peer_rank is not None:
            drivers.append(
                f"{item.vehicle_key} has a valid controlled peer position at rank "
                f"{item.peer_rank} of {item.peer_sample_size}."
            )
    if evidence.external:
        drivers.append(
            "Verified external-source metadata provides context, but does not prove "
            "causation for the internal listing signals."
        )
    if not drivers:
        drivers.append(
            "The available evidence supports description only; causal drivers are "
            "not confirmed by the current data."
        )
    return tuple(drivers[:6])


def _actions(evidence: AgentEvidence) -> tuple[str, ...]:
    actions = [
        "Monitor the next Analytics update for persistence in asking-price and "
        "listing-inventory changes.",
        "Review controlled Peer Benchmark changes before comparing vehicles "
        "across segments or powertrains.",
    ]
    if evidence.external:
        actions.append(
            "Follow the cited original sources for new verified developments."
        )
    else:
        actions.append(
            "Add verified external intelligence before attributing an internal "
            "signal to a market event."
        )
    if evidence.data_gaps:
        actions.append("Resolve the disclosed data gaps before increasing confidence.")
    return tuple(actions)


def _confidence(evidence: AgentEvidence) -> str:
    if not evidence.has_evidence:
        return "Insufficient"
    strong_vehicles = sum(
        item.available_signal_count >= 5 for item in evidence.vehicles
    )
    peer_count = sum(item.peer_status == "ok" for item in evidence.vehicles)
    if strong_vehicles and peer_count and not evidence.data_gaps:
        return "High — current internal metrics and controlled peer evidence available"
    if evidence.vehicles or evidence.alerts:
        return "Medium — grounded internal evidence with disclosed coverage gaps"
    return "Low — external context is not validated by current internal vehicle metrics"


def _parse_provider_answer(
    markdown: str,
    *,
    provider_name: str,
    evidence_sha256: str,
    evidence_records: tuple[EvidenceRecord, ...],
) -> AgentAnswer:
    if any(heading not in markdown for heading in REQUIRED_HEADINGS):
        raise IntelligenceProviderError("LLM response is missing required sections.")
    sections: dict[str, str] = {}
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1)] = markdown[match.end() : end].strip()

    def bullets(name: str) -> tuple[str, ...]:
        values = tuple(
            line[2:].strip()
            for line in sections[name].splitlines()
            if line.strip().startswith("- ")
        )
        return values or (sections[name],)

    return AgentAnswer(
        situation_summary=sections["Situation Summary"],
        evidence=bullets("Evidence"),
        key_drivers=bullets("Key Drivers"),
        competitive_implication=sections["Competitive Implication"],
        recommended_monitoring_actions=bullets("Recommended Monitoring Actions"),
        confidence_level=sections["Confidence Level"],
        generation_mode="llm_grounded",
        provider_name=provider_name,
        evidence_sha256=evidence_sha256,
        evidence_records=evidence_records,
    )


def _structured_evidence(evidence: AgentEvidence) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    analytics_date = evidence.analytics_date or "Not available"
    for item in evidence.vehicles:
        analytics_metrics = (
            ("Active listing count", item.active_listing_count),
            ("Average asking price (EUR)", item.average_asking_price_eur),
            ("7-day asking-price change (%)", item.price_change_7d_pct),
            ("30-day asking-price change (%)", item.price_change_30d_pct),
            ("7-day listing-inventory change", item.inventory_change_7d_count),
            ("7-day listing-inventory change (%)", item.inventory_change_7d_pct),
            ("New listings (7 days)", item.new_listings_count_7d),
            ("Vehicle Opportunity Score", item.opportunity_score),
        )
        quantitative_metrics = (
            ("Price Pressure Index", item.price_pressure_index),
            ("Inventory Pressure Index", item.inventory_pressure_index),
            ("Market Momentum Score", item.market_momentum_score),
        )
        records.extend(
            _metric_records(
                "Daily Market Intelligence",
                analytics_metrics,
                analytics_date,
                item.vehicle_key,
            )
        )
        records.extend(
            _metric_records(
                "Quantitative Intelligence",
                quantitative_metrics,
                analytics_date,
                item.vehicle_key,
            )
        )
        records.append(
            EvidenceRecord(
                evidence_source="Peer Benchmark",
                metric_name="Peer Status",
                value=item.peer_status,
                timestamp=analytics_date,
                vehicle_key=item.vehicle_key,
            )
        )
        if item.peer_status == "ok":
            gap_units = dict(item.peer_gap_units)
            peer_metrics: tuple[tuple[str, object | None], ...] = (
                ("Peer Match Level", item.peer_match_level),
                ("Peer Sample Size", item.peer_sample_size),
                ("Peer Rank", item.peer_rank),
                ("Peer Percentile", item.peer_percentile),
                *tuple(
                    (
                        _PEER_GAP_LABELS.get(name, name.replace("_", " ").title()),
                        _peer_gap_value(value, gap_units.get(name)),
                    )
                    for name, value in item.peer_gaps
                ),
            )
            records.extend(
                _metric_records(
                    "Peer Benchmark",
                    peer_metrics,
                    analytics_date,
                    item.vehicle_key,
                )
            )
        if item.price_history:
            history_date, history_value = item.price_history[-1]
            records.extend(
                _metric_records(
                    "SQLite Price History",
                    (("Latest average asking price (EUR)", history_value),),
                    history_date,
                    item.vehicle_key,
                )
            )
        if item.inventory_history:
            history_date, history_value = item.inventory_history[-1]
            records.extend(
                _metric_records(
                    "SQLite Inventory History",
                    (("Latest observed active inventory", history_value),),
                    history_date,
                    item.vehicle_key,
                )
            )
    for item in evidence.alerts:
        records.append(
            EvidenceRecord(
                evidence_source="Market Alerts",
                metric_name=item.alert_type,
                value=item.level or item.status,
                timestamp=item.timestamp,
                vehicle_key=item.vehicle_key,
            )
        )
        records.extend(
            _metric_records(
                "Market Alerts",
                item.related_metrics,
                item.timestamp,
                item.vehicle_key,
            )
        )
    for item in evidence.external:
        records.append(
            EvidenceRecord(
                evidence_source=f"External Market Signals · {item.source}",
                metric_name=f"{item.category.replace('_', ' ').title()} evidence",
                value=(
                    f"{item.title} · reliability {item.reliability:.0f}/100 · "
                    f"{item.region} · fetched {item.fetched_time} · {item.url}"
                ),
                timestamp=item.published_date,
            )
        )
    if evidence.external_status == NO_EVIDENCE_MESSAGE:
        records.append(
            EvidenceRecord(
                evidence_source="External Intelligence",
                metric_name="External Evidence Status",
                value=NO_EVIDENCE_MESSAGE,
                timestamp=analytics_date,
            )
        )
    return tuple(dict.fromkeys(records))


def _metric_records(
    source: str,
    metrics: tuple[tuple[str, object | None], ...],
    timestamp: str,
    vehicle_key: str,
) -> tuple[EvidenceRecord, ...]:
    return tuple(
        EvidenceRecord(
            evidence_source=source,
            metric_name=_metric_label(name),
            value=_evidence_value(value),
            timestamp=timestamp,
            vehicle_key=vehicle_key,
        )
        for name, value in metrics
        if value is not None
    )


def _evidence_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _metric_label(name: str) -> str:
    if "_" in name and name == name.casefold():
        return name.replace("_", " ").title()
    return name


def _peer_gap_value(value: float | None, unit: str | None) -> str | None:
    if value is None:
        return None
    suffix = {
        "percent": "%",
        "percentage_points": " pp",
        "points": " points",
    }.get(unit or "", f" {unit}" if unit else "")
    return f"{value:.2f}{suffix}"


def _validate_provider_markdown(
    markdown: str,
    request: AgentLLMRequest,
) -> None:
    missing = tuple(heading for heading in REQUIRED_HEADINGS if heading not in markdown)
    if missing:
        raise IntelligenceProviderError(
            f"LLM response is missing required sections: {missing}"
        )
    allowed = _numeric_tokens(
        f"{request.evidence_json}\n{request.grounded_draft_markdown}"
    )
    unsupported = _numeric_tokens(markdown) - allowed
    if unsupported:
        raise IntelligenceProviderError(
            "LLM response contains numbers absent from retrieved evidence: "
            f"{sorted(unsupported)}"
        )


def _numeric_tokens(text: str) -> set[str]:
    return {
        _normalize_number(match.group(0)) for match in _NUMBER_PATTERN.finditer(text)
    }


def _normalize_number(token: str) -> str:
    percent = token.endswith("%")
    normalized = token.removesuffix("%").replace(",", "")
    try:
        number = Decimal(normalized).normalize()
    except InvalidOperation:
        return token
    result = format(number, "f")
    return f"{result}%" if percent else result
