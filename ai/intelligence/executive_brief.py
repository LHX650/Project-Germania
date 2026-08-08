"""Evidence-grounded Germany automotive executive brief generation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ai.intelligence.agent import NO_EVIDENCE_MESSAGE, AutomotiveIntelligenceAgent
from ai.intelligence.models import AgentEvidence, EvidenceRecord, ExternalEvidence
from ai.intelligence.providers import (
    AgentLLMProvider,
    AgentLLMRequest,
    IntelligenceProviderError,
)

BRIEF_HEADINGS = (
    "## Executive Summary",
    "## Top Market Changes",
    "## Critical Risks",
    "## Top Opportunities",
    "## Competitive Movements",
    "## External News & Policy Signals",
    "## Recommended Monitoring Actions",
)
EXECUTIVE_BRIEF_SYSTEM_PROMPT = """You are the Project Germania executive analyst.
Rewrite the supplied grounded draft using only the supplied evidence packet.
Keep every required Markdown heading exactly as supplied. Do not add facts,
numbers, URLs, causal claims, sales claims, or transaction-price claims. Listing
inventory is not sales and asking prices are not transaction prices. External
signals are context only and must not be presented as causes of internal market
changes. Return insufficient_data whenever the evidence is insufficient.
"""
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")
_CAUSAL_EXTERNAL_TERMS = (
    "caused the",
    "caused by",
    "explains the",
    "led to the",
    "resulted in the",
    "drove the",
)


@dataclass(frozen=True)
class ExecutiveBrief:
    """Seven-section executive brief plus its immutable evidence register."""

    report_date: str | None
    generated_at: str
    executive_summary: str
    top_market_changes: tuple[str, ...]
    critical_risks: tuple[str, ...]
    top_opportunities: tuple[str, ...]
    competitive_movements: tuple[str, ...]
    external_news_policy_signals: tuple[str, ...]
    recommended_monitoring_actions: tuple[str, ...]
    internal_evidence: tuple[EvidenceRecord, ...]
    external_evidence: tuple[ExternalEvidence, ...]
    data_gaps: tuple[str, ...]
    confidence_level: str
    generation_mode: str
    provider_name: str
    evidence_sha256: str

    @property
    def has_internal_evidence(self) -> bool:
        """Return whether the brief contains attributable internal evidence."""

        return bool(self.internal_evidence)

    @property
    def has_external_evidence(self) -> bool:
        """Return whether the brief contains attributable external signals."""

        return bool(self.external_evidence)

    def to_markdown(self) -> str:
        """Render an auditable Markdown artifact for PDF or email conversion."""

        return (
            "# Germany Automotive Executive Brief\n\n"
            f"- Report date: {self.report_date or NO_EVIDENCE_MESSAGE}\n"
            f"- Generated at: {self.generated_at}\n"
            f"- Generation mode: {self.generation_mode}\n"
            f"- Provider: {self.provider_name}\n"
            f"- Confidence: {self.confidence_level}\n"
            f"- Evidence SHA-256: `{self.evidence_sha256}`\n\n"
            "> Scope: marketplace values are asking prices and listing activity. "
            "They are not transaction prices or vehicle sales. External market "
            "signals provide context and do not establish causation.\n\n"
            "## Executive Summary\n\n"
            f"{self.executive_summary}\n\n"
            "## Top Market Changes\n\n"
            f"{_markdown_bullets(self.top_market_changes)}\n\n"
            "## Critical Risks\n\n"
            f"{_markdown_bullets(self.critical_risks)}\n\n"
            "## Top Opportunities\n\n"
            f"{_markdown_bullets(self.top_opportunities)}\n\n"
            "## Competitive Movements\n\n"
            f"{_markdown_bullets(self.competitive_movements)}\n\n"
            "## External News & Policy Signals\n\n"
            f"{_markdown_bullets(self.external_news_policy_signals)}\n\n"
            "## Recommended Monitoring Actions\n\n"
            f"{_markdown_bullets(self.recommended_monitoring_actions)}\n\n"
            "## Internal Market Evidence\n\n"
            f"{_internal_evidence_table(self.internal_evidence)}\n\n"
            "## External Market Signals\n\n"
            f"{_external_evidence_table(self.external_evidence)}\n\n"
            "## Data Coverage\n\n"
            f"{_markdown_bullets(self.data_gaps or ('No disclosed data gaps.',))}\n"
        )


class ExecutiveBriefGenerator:
    """Generate a deterministic brief with optional grounded LLM refinement."""

    def __init__(self, provider: AgentLLMProvider | None = None) -> None:
        self._provider = provider

    def generate(
        self,
        evidence: AgentEvidence,
        *,
        generated_at: datetime | None = None,
    ) -> ExecutiveBrief:
        """Return a brief tied to the exact evidence SHA and safe local fallback."""

        timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
        draft = _local_brief(evidence, generated_at=timestamp)
        if self._provider is None:
            return draft
        request = AgentLLMRequest(
            question=evidence.question,
            intent=evidence.intent,
            evidence_sha256=evidence.sha256(),
            evidence_json=evidence.canonical_json(),
            grounded_draft_markdown=draft.to_markdown(),
            system_prompt=EXECUTIVE_BRIEF_SYSTEM_PROMPT,
        )
        try:
            result = self._provider.generate(request)
            if result.evidence_sha256 != request.evidence_sha256:
                raise IntelligenceProviderError("LLM evidence digest mismatch.")
            _validate_provider_markdown(result.markdown, request)
            return _parse_provider_brief(
                result.markdown,
                draft=draft,
                provider_name=self._provider.name,
            )
        except (IntelligenceProviderError, OSError, ValueError, RuntimeError):
            return replace(
                draft,
                generation_mode="local_rules_fallback",
                provider_name=self._provider.name,
            )


def write_executive_brief(
    brief: ExecutiveBrief,
    output_path: str | Path,
) -> Path:
    """Atomically write one complete brief while preserving the old artifact."""

    path = Path(output_path).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(brief.to_markdown(), encoding="utf-8")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def _local_brief(
    evidence: AgentEvidence,
    *,
    generated_at: datetime,
) -> ExecutiveBrief:
    records = AutomotiveIntelligenceAgent().answer(evidence).evidence_records
    internal_records = tuple(
        item for item in records if not item.evidence_source.startswith("External")
    )
    if not evidence.has_evidence:
        insufficient = (NO_EVIDENCE_MESSAGE,)
        return ExecutiveBrief(
            report_date=evidence.analytics_date,
            generated_at=generated_at.isoformat(),
            executive_summary=NO_EVIDENCE_MESSAGE,
            top_market_changes=insufficient,
            critical_risks=insufficient,
            top_opportunities=insufficient,
            competitive_movements=insufficient,
            external_news_policy_signals=insufficient,
            recommended_monitoring_actions=(
                "Wait for a valid Analytics artifact and verified external evidence.",
            ),
            internal_evidence=(),
            external_evidence=(),
            data_gaps=evidence.data_gaps or (NO_EVIDENCE_MESSAGE,),
            confidence_level="Insufficient",
            generation_mode="local_rules",
            provider_name="local_rules",
            evidence_sha256=evidence.sha256(),
        )

    return ExecutiveBrief(
        report_date=evidence.analytics_date,
        generated_at=generated_at.isoformat(),
        executive_summary=_executive_summary(evidence),
        top_market_changes=_top_market_changes(evidence),
        critical_risks=_critical_risks(evidence),
        top_opportunities=_top_opportunities(evidence),
        competitive_movements=_competitive_movements(evidence),
        external_news_policy_signals=_external_signals(evidence.external),
        recommended_monitoring_actions=_monitoring_actions(evidence),
        internal_evidence=internal_records,
        external_evidence=evidence.external,
        data_gaps=evidence.data_gaps,
        confidence_level=_confidence(evidence),
        generation_mode="local_rules",
        provider_name="local_rules",
        evidence_sha256=evidence.sha256(),
    )


def _executive_summary(evidence: AgentEvidence) -> str:
    opportunity = max(
        evidence.vehicles,
        key=lambda item: item.opportunity_score,
        default=None,
    )
    active_risks = tuple(
        item for item in evidence.alerts if item.level in {"Critical", "Warning"}
    )
    statements = [
        f"Internal Market Evidence covers {len(evidence.vehicles)} vehicles and "
        f"{len(active_risks)} active risk alerts as of "
        f"{evidence.analytics_date or NO_EVIDENCE_MESSAGE}."
    ]
    if opportunity is not None:
        statements.append(
            f"{opportunity.vehicle_key} has the highest retrieved Vehicle "
            f"Opportunity Score at {opportunity.opportunity_score:.2f}."
        )
    statements.append(
        f"External Market Signals include {len(evidence.external)} verified items; "
        "they are monitoring context and are not treated as causes of internal "
        "asking-price or listing-inventory changes."
    )
    return " ".join(statements)


def _top_market_changes(evidence: AgentEvidence) -> tuple[str, ...]:
    ranked = sorted(
        evidence.vehicles,
        key=lambda item: (
            abs(item.price_change_7d_pct or 0),
            abs(item.inventory_change_7d_pct or 0),
        ),
        reverse=True,
    )
    changes: list[str] = []
    for item in ranked:
        signals = []
        if item.price_change_7d_pct is not None:
            signals.append(
                f"7-day asking-price change {item.price_change_7d_pct:+.2f}%"
            )
        if item.inventory_change_7d_pct is not None:
            signals.append(
                "7-day listing-inventory change "
                f"{item.inventory_change_7d_pct:+.2f}%"
            )
        if signals:
            changes.append(f"{item.vehicle_key}: " + "; ".join(signals) + ".")
    return tuple(changes[:5]) or (NO_EVIDENCE_MESSAGE,)


def _critical_risks(evidence: AgentEvidence) -> tuple[str, ...]:
    risks = [
        f"{item.vehicle_key}: {item.alert_type} is {item.level}; "
        f"{item.trigger_reason}"
        for item in evidence.alerts
        if item.level in {"Critical", "Warning"}
    ]
    if risks:
        return tuple(risks[:5])
    for item in evidence.vehicles:
        signals = []
        if item.price_pressure_index is not None and item.price_pressure_index >= 70:
            signals.append(f"Price Pressure {item.price_pressure_index:.2f}")
        if (
            item.inventory_pressure_index is not None
            and item.inventory_pressure_index >= 70
        ):
            signals.append(f"Inventory Pressure {item.inventory_pressure_index:.2f}")
        if item.market_momentum_score is not None and item.market_momentum_score < 40:
            signals.append(f"Market Momentum {item.market_momentum_score:.2f}")
        if signals:
            risks.append(f"{item.vehicle_key}: " + "; ".join(signals) + ".")
    return tuple(risks[:5]) or (
        "No retrieved internal signal crosses the available risk thresholds.",
    )


def _top_opportunities(evidence: AgentEvidence) -> tuple[str, ...]:
    ranked = sorted(
        evidence.vehicles,
        key=lambda item: item.opportunity_score,
        reverse=True,
    )
    return tuple(
        f"{item.vehicle_key}: Vehicle Opportunity Score "
        f"{item.opportunity_score:.2f}; Market Momentum "
        f"{_optional_score(item.market_momentum_score, item.market_momentum_label)}."
        for item in ranked[:5]
    ) or (NO_EVIDENCE_MESSAGE,)


def _competitive_movements(evidence: AgentEvidence) -> tuple[str, ...]:
    movements = []
    for item in evidence.vehicles:
        if item.peer_status != "ok" or item.peer_rank is None:
            continue
        gaps = dict(item.peer_gaps)
        gap_text = []
        for label, key, suffix in (
            ("Price Gap", "price_gap_pct", "%"),
            ("Opportunity Gap", "opportunity_score_gap", " points"),
            ("Momentum Gap", "market_momentum_gap", " points"),
        ):
            value = gaps.get(key)
            if value is not None:
                gap_text.append(f"{label} {value:+.2f}{suffix}")
        movement = (
            f"{item.vehicle_key}: peer rank {item.peer_rank}/"
            f"{item.peer_sample_size + 1}, percentile "
            f"{_optional_score(item.peer_percentile)}"
        )
        if gap_text:
            movement += "; " + "; ".join(gap_text)
        movements.append(movement + ".")
    return tuple(movements[:5]) or (NO_EVIDENCE_MESSAGE,)


def _external_signals(
    evidence: tuple[ExternalEvidence, ...],
) -> tuple[str, ...]:
    return tuple(
        f"{item.source} | {item.category.replace('_', ' ').title()} | "
        f"{item.published_date}: [{item.title}]({item.url}) "
        f"(reliability {item.reliability:.0f}/100, {item.region})."
        for item in evidence[:8]
    ) or (NO_EVIDENCE_MESSAGE,)


def _monitoring_actions(evidence: AgentEvidence) -> tuple[str, ...]:
    actions = [
        "Verify whether current asking-price and listing-inventory changes persist "
        "in the next daily Analytics update.",
        "Review controlled Peer Benchmark rank and gap changes before escalating "
        "a competitive-position conclusion.",
    ]
    if evidence.alerts:
        actions.append(
            "Re-evaluate active Market Alerts after the next comparable observation."
        )
    if evidence.external:
        actions.append(
            "Review cited official sources for updates while keeping external "
            "signals separate from internal metric causality."
        )
    else:
        actions.append(
            "Obtain verified external evidence before attributing internal changes "
            "to a market event."
        )
    if evidence.data_gaps:
        actions.append("Resolve disclosed data gaps before increasing confidence.")
    return tuple(actions)


def _confidence(evidence: AgentEvidence) -> str:
    if not evidence.has_evidence:
        return "Insufficient"
    internal = sum(item.available_signal_count >= 5 for item in evidence.vehicles)
    peers = sum(item.peer_status == "ok" for item in evidence.vehicles)
    if internal and peers and evidence.external and not evidence.data_gaps:
        return "High"
    if evidence.vehicles or evidence.alerts:
        return "Medium"
    return "Low"


def _parse_provider_brief(
    markdown: str,
    *,
    draft: ExecutiveBrief,
    provider_name: str,
) -> ExecutiveBrief:
    sections = _sections(markdown)
    return replace(
        draft,
        executive_summary=sections["Executive Summary"],
        top_market_changes=_section_bullets(sections["Top Market Changes"]),
        critical_risks=_section_bullets(sections["Critical Risks"]),
        top_opportunities=_section_bullets(sections["Top Opportunities"]),
        competitive_movements=_section_bullets(sections["Competitive Movements"]),
        external_news_policy_signals=_section_bullets(
            sections["External News & Policy Signals"]
        ),
        recommended_monitoring_actions=_section_bullets(
            sections["Recommended Monitoring Actions"]
        ),
        generation_mode="llm_grounded",
        provider_name=provider_name,
    )


def _validate_provider_markdown(
    markdown: str,
    request: AgentLLMRequest,
) -> None:
    missing = tuple(heading for heading in BRIEF_HEADINGS if heading not in markdown)
    if missing:
        raise IntelligenceProviderError(
            f"LLM executive brief is missing required sections: {missing}"
        )
    allowed = _numeric_tokens(
        f"{request.evidence_json}\n{request.grounded_draft_markdown}"
    )
    unsupported = _numeric_tokens(markdown) - allowed
    if unsupported:
        raise IntelligenceProviderError(
            "LLM executive brief contains numbers absent from evidence: "
            f"{sorted(unsupported)}"
        )
    external_section = _sections(markdown)["External News & Policy Signals"].casefold()
    if any(term in external_section for term in _CAUSAL_EXTERNAL_TERMS):
        raise IntelligenceProviderError(
            "LLM executive brief asserted causation from an external signal."
        )


def _sections(markdown: str) -> dict[str, str]:
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1)] = markdown[match.end() : end].strip()
    return sections


def _section_bullets(section: str) -> tuple[str, ...]:
    values = tuple(
        line[2:].strip()
        for line in section.splitlines()
        if line.strip().startswith("- ")
    )
    return values or (section or NO_EVIDENCE_MESSAGE,)


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


def _optional_score(value: float | None, label: str | None = None) -> str:
    if value is None:
        return NO_EVIDENCE_MESSAGE
    suffix = f" ({label})" if label and label != NO_EVIDENCE_MESSAGE else ""
    return f"{value:.2f}{suffix}"


def _markdown_bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _escape_table(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _internal_evidence_table(records: tuple[EvidenceRecord, ...]) -> str:
    if not records:
        return NO_EVIDENCE_MESSAGE
    rows = [
        "| Evidence Source | Metric Name | Value | Timestamp | Vehicle |",
        "| --- | --- | ---: | --- | --- |",
    ]
    rows.extend(
        "| "
        + " | ".join(
            _escape_table(value)
            for value in (
                item.evidence_source,
                item.metric_name,
                item.value,
                item.timestamp,
                item.vehicle_key or "",
            )
        )
        + " |"
        for item in records
    )
    return "\n".join(rows)


def _external_evidence_table(records: tuple[ExternalEvidence, ...]) -> str:
    if not records:
        return NO_EVIDENCE_MESSAGE
    rows = [
        "| Source | Category | Published | Reliability | Region | Evidence |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    rows.extend(
        "| "
        + " | ".join(
            _escape_table(value)
            for value in (
                item.source,
                item.category,
                item.published_date,
                f"{item.reliability:.0f}/100",
                item.region,
                f"[{item.title}]({item.url})",
            )
        )
        + " |"
        for item in records
    )
    return "\n".join(rows)
