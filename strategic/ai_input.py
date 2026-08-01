"""Strict read-only parser for the upstream AI Market Report."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AIReportInputError(ValueError):
    """Raised when the upstream AI Markdown cannot be trusted as input."""


@dataclass(frozen=True)
class AIReportEvidence:
    """Validated AI report metadata and sections."""

    report_date: date
    generation_mode: str
    provider_name: str | None
    evidence_sha256: str | None
    sections: dict[str, str]
    source_path: Path


def load_ai_report_evidence(path: str | Path) -> AIReportEvidence:
    """Load a Phase 6 AI report without importing Dashboard code."""

    source_path = Path(path).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise AIReportInputError(f"AI report does not exist: {source_path}")
    try:
        markdown = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AIReportInputError("AI report is not readable UTF-8 Markdown.") from exc
    if not markdown.strip():
        raise AIReportInputError("AI report is empty.")
    report_date_text = _metadata(markdown, "Analytics date", required=True)
    try:
        report_date = date.fromisoformat(report_date_text or "")
    except ValueError as exc:
        raise AIReportInputError(
            "AI report Analytics date must use YYYY-MM-DD."
        ) from exc
    generation_mode = _metadata(markdown, "Generation mode", required=True)
    provider_name = _metadata(markdown, "LLM provider", required=False)
    if provider_name == "none":
        provider_name = None
    digest = _metadata(markdown, "Analytics evidence SHA-256", required=False)
    if digest is not None and _SHA256_PATTERN.fullmatch(digest) is None:
        raise AIReportInputError("AI report Analytics evidence SHA-256 is invalid.")
    sections = _sections(markdown)
    required_sections = {
        "Germany market overview",
        "Vehicle opportunity analysis",
        "Risk and opportunity summary",
    }
    missing = required_sections - sections.keys()
    if missing:
        raise AIReportInputError(
            "AI report is missing required sections: " + ", ".join(sorted(missing))
        )
    return AIReportEvidence(
        report_date=report_date,
        generation_mode=generation_mode or "unknown",
        provider_name=provider_name,
        evidence_sha256=digest,
        sections=sections,
        source_path=source_path,
    )


def _metadata(markdown: str, label: str, *, required: bool) -> str | None:
    pattern = re.compile(
        rf"^\*\*{re.escape(label)}:\*\*\s+`?(?P<value>[^`\r\n]+?)`?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(markdown)
    if match is None:
        if required:
            raise AIReportInputError(f"AI report metadata is missing: {label}")
        return None
    value = match.group("value").strip()
    if required and not value:
        raise AIReportInputError(f"AI report metadata is empty: {label}")
    return value or None


def _sections(markdown: str) -> dict[str, str]:
    matches = tuple(_SECTION_PATTERN.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        if title in sections:
            raise AIReportInputError(f"AI report repeats section: {title}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[match.end() : end].strip()
        if not body:
            raise AIReportInputError(f"AI report section is empty: {title}")
        sections[title] = body
    return sections
