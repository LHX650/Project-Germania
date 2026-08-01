"""Grounded German automotive market analysis with optional LLM enhancement."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from ai.models import DailyMarketIntelligence
from ai.providers import LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = (
    "## Germany market overview",
    "## Brand competition analysis",
    "## Vehicle opportunity analysis",
    "## Price trend interpretation",
    "## Inventory change interpretation",
    "## Risk and opportunity summary",
)
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")


@dataclass(frozen=True)
class GeneratedAIReport:
    """Generated Markdown plus transparent generation provenance."""

    markdown: str
    generation_mode: str
    provider_name: str | None
    fallback_reason: str | None
    evidence_sha256: str


def generate_ai_market_report(
    report: DailyMarketIntelligence,
    *,
    provider: LLMProvider | None = None,
) -> GeneratedAIReport:
    """Generate a grounded report, falling back locally if an LLM is unusable."""

    evidence_json = _evidence_json(report)
    evidence_sha256 = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
    local_markdown = _local_rule_report(report)
    if provider is None:
        return GeneratedAIReport(
            markdown=_add_provenance(
                local_markdown,
                "local_rules",
                None,
                evidence_sha256,
            ),
            generation_mode="local_rules",
            provider_name=None,
            fallback_reason=None,
            evidence_sha256=evidence_sha256,
        )

    request = LLMRequest(
        report_date=report.report_date.isoformat(),
        evidence_sha256=evidence_sha256,
        evidence_json=evidence_json,
        grounded_draft_markdown=local_markdown,
        instructions=(
            "Use only the supplied Analytics evidence.",
            "Do not add external market facts, causes, sales claims, or forecasts.",
            "Keep asking prices distinct from transaction prices.",
            "Keep listing inventory distinct from registrations or sales.",
            "Preserve all required Markdown section headings.",
        ),
    )
    try:
        candidate = provider.generate(request)
        _validate_provider_result(
            candidate.markdown,
            candidate.evidence_sha256,
            request=request,
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Optional LLM provider unavailable or ungrounded; using local fallback "
            "provider=%s reason=%s",
            provider.name,
            reason,
        )
        return GeneratedAIReport(
            markdown=_add_provenance(
                local_markdown,
                "local_rules_fallback",
                provider.name,
                evidence_sha256,
            ),
            generation_mode="local_rules_fallback",
            provider_name=provider.name,
            fallback_reason=reason,
            evidence_sha256=evidence_sha256,
        )

    return GeneratedAIReport(
        markdown=_add_provenance(
            candidate.markdown,
            "llm_grounded",
            provider.name,
            evidence_sha256,
        ),
        generation_mode="llm_grounded",
        provider_name=provider.name,
        fallback_reason=None,
        evidence_sha256=evidence_sha256,
    )


def _local_rule_report(report: DailyMarketIntelligence) -> str:
    sections = (
        "# AI-powered German Automotive Market Report",
        "",
        f"**Analytics date:** {report.report_date.isoformat()}  ",
        "**Source:** `reports/daily_market_intelligence.json`  ",
        "**Evidence scope:** Project Germania marketplace asking-price and active-"
        "inventory analytics.",
        "",
        "> Asking prices are not confirmed transaction prices. Listing inventory "
        "is not vehicle sales or new registrations. Interpretations below are "
        "derived only from the supplied Analytics report.",
        "",
        "## Germany market overview",
        "",
        _market_overview(report),
        "",
        "## Brand competition analysis",
        "",
        _brand_analysis(report),
        "",
        "## Vehicle opportunity analysis",
        "",
        _vehicle_opportunity_analysis(report),
        "",
        "## Price trend interpretation",
        "",
        _price_trend_analysis(report),
        "",
        "## Inventory change interpretation",
        "",
        _inventory_analysis(report),
        "",
        "## Risk and opportunity summary",
        "",
        _risk_opportunity_summary(report),
        "",
        "---",
        "",
        "This is a Project Germania analytical model output, not an official "
        "market ranking, confirmed sales report, transaction-price report, or "
        "investment recommendation.",
    )
    return "\n".join(sections).strip() + "\n"


def _market_overview(report: DailyMarketIntelligence) -> str:
    if not report.vehicles and not report.brands:
        return (
            "The Analytics input contains no vehicle or brand observations. No market "
            "overview can be inferred, and no values have been imputed."
        )
    average_price = _eur(report.weighted_average_price_eur)
    return (
        f"The tracked Germany marketplace scope contains "
        f"**{report.active_inventory_count:,} active listings** across "
        f"**{len(report.vehicles)} vehicle models** and **{len(report.brands)} "
        f"brands**. The listing-weighted mean asking price is **{average_price}**. "
        f"The report records **{report.new_listings_count_7d:,} newly observed "
        f"listings over seven days** and a net inferred inventory change of "
        f"**{report.inventory_change_7d_count:+,} listings** over that window."
    )


def _brand_analysis(report: DailyMarketIntelligence) -> str:
    if not report.brands:
        return "Brand competition data is unavailable in the Analytics input."
    ranked = sorted(
        report.brands,
        key=lambda item: (
            item.metrics.active_inventory_rank,
            item.brand.casefold(),
        ),
    )
    bullets = []
    for item in ranked[:5]:
        metrics = item.metrics
        model_coverage = _coverage(
            metrics.model_coverage_count,
            metrics.catalog_model_count,
            metrics.model_coverage_pct,
        )
        bullets.append(
            f"- **{item.brand}** ranks **#{metrics.active_inventory_rank}** with "
            f"**{metrics.active_inventory_count:,} active listings**, an average "
            f"asking price of **{_eur(metrics.average_vehicle_price_eur)}**, "
            f"BEV/PHEV share of **{_pct(metrics.bev_phev_share_pct)}**, and model "
            f"coverage of **{model_coverage}**."
        )
    return (
        "Active-inventory ranking within the tracked dataset is:\n\n"
        + "\n".join(bullets)
        + "\n\nThis ranking measures observed marketplace inventory, not brand sales."
    )


def _vehicle_opportunity_analysis(report: DailyMarketIntelligence) -> str:
    if not report.vehicles:
        return "Vehicle opportunity scoring is unavailable because no vehicles exist."
    ranked = sorted(
        report.vehicles,
        key=lambda item: (
            -item.opportunity_score.score,
            item.brand.casefold(),
            item.model.casefold(),
        ),
    )
    bullets = [
        (
            f"- **{item.brand} {item.model}**: opportunity score "
            f"**{item.opportunity_score.score:.2f}/100**, "
            f"**{item.metrics.active_listing_count:,} active listings**, average "
            f"asking price **{_eur(item.metrics.average_price_eur)}**, and "
            f"**{item.metrics.new_listings_count_7d:,} seven-day new listings**."
        )
        for item in ranked[:5]
    ]
    return (
        "The highest project-model opportunity scores are:\n\n"
        + "\n".join(bullets)
        + "\n\nScores combine inventory attractiveness, price competitiveness, price "
        "trend when available, and market activity using the Analytics methodology."
    )


def _price_trend_analysis(report: DailyMarketIntelligence) -> str:
    if not report.vehicles:
        return "No vehicle price observations are available for interpretation."
    seven_day = tuple(
        item for item in report.vehicles if item.metrics.price_change_7d_pct is not None
    )
    thirty_day = tuple(
        item
        for item in report.vehicles
        if item.metrics.price_change_30d_pct is not None
    )
    if not seven_day and not thirty_day:
        return (
            "No valid seven-day or thirty-day price baselines are available. The "
            "report therefore makes no directional price claim."
        )
    lines = [
        f"Price-trend coverage is **{len(seven_day)}/{len(report.vehicles)} "
        f"vehicles for seven days** and **{len(thirty_day)}/{len(report.vehicles)} "
        "vehicles for thirty days**."
    ]
    if seven_day:
        declining = sorted(
            (item for item in seven_day if item.metrics.price_change_7d_pct < 0),
            key=lambda item: item.metrics.price_change_7d_pct,
        )
        increasing = sorted(
            (item for item in seven_day if item.metrics.price_change_7d_pct > 0),
            key=lambda item: item.metrics.price_change_7d_pct,
            reverse=True,
        )
        stable_count = len(seven_day) - len(declining) - len(increasing)
        lines.append(
            f"Among vehicles with seven-day coverage, **{len(declining)} declined**, "
            f"**{len(increasing)} increased**, and **{stable_count} were unchanged**."
        )
        if declining:
            item = declining[0]
            lines.append(
                f"The largest observed decline is **{item.brand} {item.model}** at "
                f"**{_pct(item.metrics.price_change_7d_pct, signed=True)}**."
            )
        if increasing:
            item = increasing[0]
            lines.append(
                f"The largest observed increase is **{item.brand} {item.model}** at "
                f"**{_pct(item.metrics.price_change_7d_pct, signed=True)}**."
            )
    lines.append(
        "Changes compare reconstructed mean asking-price snapshots and may reflect "
        "listing-composition changes as well as price changes."
    )
    return " ".join(lines)


def _inventory_analysis(report: DailyMarketIntelligence) -> str:
    if not report.vehicles:
        return "No vehicle inventory observations are available for interpretation."
    increasing = sorted(
        (
            item
            for item in report.vehicles
            if item.metrics.inventory_change_7d_count > 0
        ),
        key=lambda item: item.metrics.inventory_change_7d_count,
        reverse=True,
    )
    decreasing = sorted(
        (
            item
            for item in report.vehicles
            if item.metrics.inventory_change_7d_count < 0
        ),
        key=lambda item: item.metrics.inventory_change_7d_count,
    )
    unchanged = len(report.vehicles) - len(increasing) - len(decreasing)
    lines = [
        f"Across tracked vehicles, **{len(increasing)} show higher inventory**, "
        f"**{len(decreasing)} show lower inventory**, and **{unchanged} are "
        "unchanged** over seven days."
    ]
    if increasing:
        item = increasing[0]
        lines.append(
            f"The largest increase is **{item.brand} {item.model}** at "
            f"**{item.metrics.inventory_change_7d_count:+,} listings**."
        )
    if decreasing:
        item = decreasing[0]
        lines.append(
            f"The largest decrease is **{item.brand} {item.model}** at "
            f"**{item.metrics.inventory_change_7d_count:+,} listings**."
        )
    lines.append(
        "Inventory history is inferred from first/last-seen windows and active state; "
        "a decline is not confirmation of a sale or permanent delisting."
    )
    return " ".join(lines)


def _risk_opportunity_summary(report: DailyMarketIntelligence) -> str:
    if not report.vehicles:
        return (
            "- **Opportunity:** No data-supported opportunity can be stated.\n"
            "- **Risk:** The input is empty, so market conclusions are unavailable."
        )
    ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    top = ranked[0]
    seven_day_coverage = sum(
        item.metrics.price_change_7d_pct is not None for item in report.vehicles
    )
    thirty_day_coverage = sum(
        item.metrics.price_change_30d_pct is not None for item in report.vehicles
    )
    return (
        f"- **Opportunity:** **{top.brand} {top.model}** has the highest available "
        f"project opportunity score at **{top.opportunity_score.score:.2f}/100**; "
        "this identifies a research priority, not an investment recommendation.\n"
        f"- **Activity signal:** The tracked scope added **"
        f"{report.new_listings_count_7d:,} new listings** over seven days.\n"
        f"- **Trend-data risk:** Price-change coverage is **{seven_day_coverage}/"
        f"{len(report.vehicles)} for seven days** and **{thirty_day_coverage}/"
        f"{len(report.vehicles)} for thirty days**; missing baselines constrain "
        "trend interpretation.\n"
        "- **Measurement risk:** Marketplace inventory and asking prices do not "
        "establish registrations, completed transactions, demand, or causal drivers."
    )


def _evidence_json(report: DailyMarketIntelligence) -> str:
    payload = {
        "date": report.report_date.isoformat(),
        "vehicles": [asdict(item) for item in report.vehicles],
        "brands": [asdict(item) for item in report.brands],
        "methodology": report.methodology,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _validate_provider_result(
    markdown: str,
    evidence_sha256: str,
    *,
    request: LLMRequest,
) -> None:
    if evidence_sha256 != request.evidence_sha256:
        raise ValueError("LLM result evidence digest does not match the request")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("LLM result must contain non-empty Markdown")
    missing = [section for section in REQUIRED_SECTIONS if section not in markdown]
    if missing:
        raise ValueError(f"LLM result is missing required sections: {missing}")
    allowed_numbers = _numeric_tokens(
        f"{request.evidence_json}\n{request.grounded_draft_markdown}"
    )
    candidate_numbers = _numeric_tokens(markdown)
    unsupported = candidate_numbers - allowed_numbers
    if unsupported:
        raise ValueError(
            "LLM result contains numbers absent from Analytics evidence: "
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
        value = Decimal(normalized)
    except InvalidOperation:
        return token
    suffix = "%" if percent else ""
    return f"{value.normalize()}{suffix}"


def _add_provenance(
    markdown: str,
    mode: str,
    provider_name: str | None,
    evidence_sha256: str,
) -> str:
    lines = markdown.strip().splitlines()
    provider = provider_name or "none"
    provenance = (
        f"**Generation mode:** `{mode}`  \n"
        f"**LLM provider:** `{provider}`  \n"
        f"**Analytics evidence SHA-256:** `{evidence_sha256}`  "
    )
    insert_at = 1 if lines and lines[0].startswith("# ") else 0
    lines[insert_at:insert_at] = ["", provenance]
    return "\n".join(lines).strip() + "\n"


def _eur(value: float | None) -> str:
    return "unavailable" if value is None else f"EUR {value:,.0f}"


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "unavailable"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:.2f}%"


def _coverage(count: int, total: int, percentage: float | None) -> str:
    if percentage is None:
        return f"{count}/{total} (percentage unavailable)"
    return f"{count}/{total} ({percentage:.2f}%)"
