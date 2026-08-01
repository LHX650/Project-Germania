"""Management-facing strategic Markdown rendering and atomic persistence."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from strategic.analysis import StrategicAnalysis, StrategicFinding
from strategic.external import ExternalSignal, ExternalSourceSnapshot

logger = logging.getLogger(__name__)


def render_strategic_market_report(
    analysis: StrategicAnalysis,
    *,
    analytics_source: Path,
    ai_source: Path,
    generated_at_utc: datetime | None = None,
) -> str:
    """Render a transparent management report from structured findings."""

    generated_at = generated_at_utc or datetime.now(UTC)
    external_signal_count = analysis.external_intelligence.available_signal_count
    lines = [
        "# Project Germania Strategic Market Report",
        "",
        f"**Strategic report date:** {analysis.report_date}  ",
        f"**Generated at (UTC):** {generated_at.astimezone(UTC).isoformat()}  ",
        f"**Analytics input:** `{analytics_source.name}`  ",
        f"**AI report input:** `{ai_source.name}`  ",
        f"**AI generation mode:** `{analysis.ai_generation_mode}`  ",
        "**Analytics evidence SHA-256:** "
        + (
            f"`{analysis.ai_evidence_sha256}`  "
            if analysis.ai_evidence_sha256
            else "unavailable  "
        ),
        "",
        "> This report is Project Germania decision support. Marketplace listing "
        "inventory is not sales or registrations, asking prices are not confirmed "
        "transaction prices, and opportunity scores are project-model outputs.",
        "",
        "## Executive strategic summary",
        "",
        (
            f"The strategic layer identified **{len(analysis.opportunities)} market "
            f"opportunity findings**, **{len(analysis.competitive_risks)} competitive "
            f"risk findings**, and **{len(analysis.recommendations)} management "
            "actions**. "
            f"External providers supplied **{external_signal_count} "
            "source-attributed signals**. Recommendations remain gated where "
            "independent evidence is unavailable."
        ),
        "",
        "## Market Opportunity",
        "",
        *_finding_lines(analysis.opportunities),
        "## Competitive Risk",
        "",
        *_finding_lines(analysis.competitive_risks),
        "## Strategic Recommendation",
        "",
    ]
    for recommendation in sorted(
        analysis.recommendations,
        key=lambda item: item.priority,
    ):
        lines.extend(
            (
                f"### Priority {recommendation.priority}: {recommendation.action}",
                "",
                recommendation.rationale,
                "",
                f"**Decision gate:** {recommendation.decision_gate}",
                "",
            )
        )
    lines.extend(
        (
            "## External Intelligence Status",
            "",
            "| Source | Provider | Status | Signals |",
            "| --- | --- | --- | ---: |",
        )
    )
    for snapshot in analysis.external_intelligence.snapshots:
        lines.append(_snapshot_row(snapshot))
    lines.extend(("", "## External Evidence Register", ""))
    signal_count = 0
    for snapshot in analysis.external_intelligence.snapshots:
        for signal in snapshot.signals:
            signal_count += 1
            lines.extend(_signal_lines(snapshot, signal))
    if signal_count == 0:
        lines.append(
            "No source-attributed external signals were available for this run."
        )
    lines.extend(("", "## Management Data Gaps", ""))
    if analysis.data_gaps:
        lines.extend(f"- {gap}" for gap in analysis.data_gaps)
    else:
        lines.append("- No configured-source gap was reported for this run.")
    lines.extend(
        (
            "",
            "## Methodology and Guardrails",
            "",
            "- Market opportunities rank the current transparent Analytics "
            "opportunity score and preserve its underlying listing metrics.",
            "- Competitive risks disclose price-history coverage, observed "
            "inventory concentration, and AI-report measurement limitations.",
            "- External facts are included only when a configured provider returns "
            "source-attributed signals with an observation date and URL.",
            "- Missing or failed external providers are reported as data gaps; their "
            "absence is never converted into a market claim.",
            "- Strategic recommendations are management research priorities, not "
            "forecasts, official rankings, or investment recommendations.",
            "",
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def write_strategic_market_report(markdown: str, output_path: str | Path) -> Path:
    """Atomically write a complete strategic report and preserve the old file."""

    path = Path(output_path).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(markdown, encoding="utf-8")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    logger.info("Wrote strategic market report path=%s", path)
    return path


def _finding_lines(findings: tuple[StrategicFinding, ...]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        lines.extend(
            (
                f"### {finding.headline}",
                "",
                finding.analysis,
                "",
                f"**Evidence level:** `{finding.evidence_level}`",
                "",
                *[f"- {item}" for item in finding.evidence],
                "",
            )
        )
    return lines


def _snapshot_row(snapshot: ExternalSourceSnapshot) -> str:
    values = (
        snapshot.source_type.value,
        snapshot.provider_name,
        snapshot.status.value,
        str(len(snapshot.signals)),
    )
    escaped = tuple(_table_value(value) for value in values)
    return f"| {' | '.join(escaped)} |"


def _signal_lines(
    snapshot: ExternalSourceSnapshot,
    signal: ExternalSignal,
) -> tuple[str, ...]:
    observed_at = signal.observed_at.isoformat()
    metric = ""
    if signal.metric_name and signal.metric_value is not None:
        unit = f" {signal.unit}" if signal.unit else ""
        metric = f"- **Metric:** {signal.metric_name} = {signal.metric_value}{unit}"
    lines = [
        f"### {signal.title}",
        "",
        signal.summary,
        "",
        f"- **Source type:** `{snapshot.source_type.value}`",
        f"- **Provider:** `{snapshot.provider_name}`",
        f"- **Implication:** `{signal.implication.value}`",
        f"- **Observed at:** {observed_at}",
    ]
    if metric:
        lines.append(metric)
    lines.extend((f"- **Source:** [{signal.source_url}]({signal.source_url})", ""))
    return tuple(lines)


def _table_value(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
