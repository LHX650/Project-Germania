"""Validated, cached, read-only access to the daily AI Markdown report."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from services.runtime import get_dashboard_data_paths

DEFAULT_AI_REPORT_RELATIVE_PATH = Path("reports/daily_ai_market_report.md")
MARKET_OVERVIEW_SECTION = "Germany market overview"
VEHICLE_OPPORTUNITY_SECTION = "Vehicle opportunity analysis"
RISK_OPPORTUNITY_SECTION = "Risk and opportunity summary"
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_LABELED_BULLET_PATTERN = re.compile(
    r"^-\s+\*\*(?P<label>[^*]+):\*\*\s*(?P<body>.+?)\s*$",
    re.MULTILINE,
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AIReportError(RuntimeError):
    """Raised when the AI report is missing, unreadable, or invalid."""


@dataclass(frozen=True)
class AIMarketReport:
    """Structured view of one grounded AI market report."""

    title: str
    generation_mode: str
    provider_name: str | None
    analytics_date: date
    evidence_sha256: str | None
    generated_at_utc: datetime
    sections: dict[str, str]
    raw_markdown: str
    source_path: Path

    @property
    def market_overview_markdown(self) -> str:
        """Return the latest AI market summary section."""

        return self.sections[MARKET_OVERVIEW_SECTION]

    @property
    def vehicle_opportunity_markdown(self) -> str:
        """Return the dynamically generated key-vehicle analysis."""

        return self.sections[VEHICLE_OPPORTUNITY_SECTION]

    @property
    def market_opportunity_markdown(self) -> str:
        """Return opportunity bullets without inventing replacement content."""

        section = self.sections[RISK_OPPORTUNITY_SECTION]
        opportunity_bullets = tuple(
            bullet
            for label, bullet in _labeled_bullets(section)
            if label.casefold() in {"opportunity", "activity signal"}
        )
        if opportunity_bullets:
            return "\n".join(opportunity_bullets)
        return self.vehicle_opportunity_markdown

    @property
    def risk_markdown(self) -> str:
        """Return risk-labeled bullets from the report's final summary."""

        section = self.sections[RISK_OPPORTUNITY_SECTION]
        risk_bullets = tuple(
            bullet
            for label, bullet in _labeled_bullets(section)
            if "risk" in label.casefold()
        )
        return "\n".join(risk_bullets) if risk_bullets else section


def get_project_root() -> Path:
    """Return the absolute Project Germania root directory."""

    return Path(__file__).resolve().parents[2]


def resolve_ai_report_path(report_path: str | Path | None = None) -> Path:
    """Resolve an AI report path without creating or modifying it."""

    candidate = (
        Path(report_path).expanduser()
        if report_path is not None
        else get_dashboard_data_paths().ai_market_report
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return candidate.resolve(strict=False)


def load_daily_ai_market_report(
    report_path: str | Path | None = None,
) -> AIMarketReport:
    """Load the latest report, automatically refreshing after file changes."""

    path = resolve_ai_report_path(report_path)
    if not path.is_file():
        raise AIReportError(
            "AI market report was not found. Generate "
            "reports/daily_ai_market_report.md before opening this page."
        )
    try:
        stat = path.stat()
    except OSError as exc:
        raise AIReportError("Unable to inspect the AI market report.") from exc
    return _load_cached(str(path), stat.st_mtime_ns, stat.st_size)


def clear_ai_report_cache() -> None:
    """Clear the in-process report cache for tests and operations."""

    _load_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_cached(
    path_text: str,
    modified_at_ns: int,
    file_size: int,
) -> AIMarketReport:
    del file_size
    path = Path(path_text)
    try:
        markdown = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AIReportError(
            "AI market report is unreadable or is not valid UTF-8 Markdown."
        ) from exc
    generated_at = datetime.fromtimestamp(modified_at_ns / 1_000_000_000, tz=UTC)
    return _parse_report(markdown, source_path=path, generated_at_utc=generated_at)


def _parse_report(
    markdown: str,
    *,
    source_path: Path,
    generated_at_utc: datetime,
) -> AIMarketReport:
    if not markdown.strip():
        raise AIReportError("AI market report is empty.")
    title = _title(markdown)
    generation_mode = _required_metadata(markdown, "Generation mode")
    provider_name = _optional_metadata(markdown, "LLM provider")
    if provider_name == "none":
        provider_name = None
    analytics_date_text = _required_metadata(markdown, "Analytics date")
    try:
        analytics_date = date.fromisoformat(analytics_date_text)
    except ValueError as exc:
        raise AIReportError("AI report Analytics date must use YYYY-MM-DD.") from exc
    evidence_sha256 = _optional_metadata(markdown, "Analytics evidence SHA-256")
    if (
        evidence_sha256 is not None
        and _SHA256_PATTERN.fullmatch(evidence_sha256) is None
    ):
        raise AIReportError("AI report evidence SHA-256 is invalid.")
    sections = _sections(markdown)
    missing_sections = {
        MARKET_OVERVIEW_SECTION,
        VEHICLE_OPPORTUNITY_SECTION,
        RISK_OPPORTUNITY_SECTION,
    } - sections.keys()
    if missing_sections:
        missing = ", ".join(sorted(missing_sections))
        raise AIReportError(
            f"AI market report is missing required sections: {missing}."
        )
    return AIMarketReport(
        title=title,
        generation_mode=generation_mode,
        provider_name=provider_name,
        analytics_date=analytics_date,
        evidence_sha256=evidence_sha256,
        generated_at_utc=generated_at_utc,
        sections=sections,
        raw_markdown=markdown,
        source_path=source_path,
    )


def _title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line.removeprefix("# ").strip()
            if title:
                return title
    raise AIReportError("AI market report must contain a top-level title.")


def _required_metadata(markdown: str, label: str) -> str:
    value = _optional_metadata(markdown, label)
    if value is None:
        raise AIReportError(f"AI market report is missing metadata: {label}.")
    return value


def _optional_metadata(markdown: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\*\*{re.escape(label)}:\*\*\s+`?(?P<value>[^`\r\n]+?)`?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(markdown)
    return match.group("value").strip() if match is not None else None


def _sections(markdown: str) -> dict[str, str]:
    matches = tuple(_HEADING_PATTERN.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        if heading in sections:
            raise AIReportError(f"AI market report repeats section: {heading}.")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[match.end() : end].strip()
        if not body:
            raise AIReportError(f"AI market report section is empty: {heading}.")
        sections[heading] = body
    return sections


def _labeled_bullets(markdown: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            match.group("label").strip(),
            f"- **{match.group('label').strip()}:** {match.group('body').strip()}",
        )
        for match in _LABELED_BULLET_PATTERN.finditer(markdown)
    )
