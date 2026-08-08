"""Read-only evidence assembly for the daily Executive Intelligence Brief."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from ai.intelligence.executive_brief import (
    ExecutiveBrief,
    ExecutiveBriefGenerator,
    write_executive_brief,
)
from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import (
    AgentLLMProvider,
    EmptyExternalIntelligenceProvider,
    ExternalIntelligenceProvider,
    ExternalQuery,
    IntelligenceProviderError,
)
from services.ai_agent import _configured_llm_provider, retrieve_evidence
from services.external_intelligence import build_default_external_provider
from services.intelligence import DailyMarketIntelligence
from services.runtime import get_dashboard_data_paths, get_project_root

DEFAULT_EXECUTIVE_BRIEF_PATH = Path("reports/daily_executive_intelligence_brief.md")
_ARTIFACT_SECTIONS = (
    "Executive Summary",
    "Top Market Changes",
    "Critical Risks",
    "Top Opportunities",
    "Competitive Movements",
    "External News & Policy Signals",
    "Recommended Monitoring Actions",
    "Internal Market Evidence",
    "External Market Signals",
    "Data Coverage",
)
_EXECUTIVE_EXTERNAL_CATEGORIES = frozenset(
    {
        "news",
        "automotive_news",
        "policy_regulation",
        "brand_intelligence",
        "industry_report",
    }
)
_BRIEF_QUESTION = (
    "Germany automotive daily market brief overview: top market changes, "
    "critical risks, top opportunities, competitive movements, external news "
    "and policy signals, and recommended monitoring actions."
)


class ExecutiveBriefArtifactError(RuntimeError):
    """Raised when the persisted daily Brief is missing or invalid."""


@dataclass(frozen=True)
class ExecutiveBriefArtifact:
    """Validated, read-only representation of a persisted Brief artifact."""

    report_date: date
    generated_at: datetime
    generation_mode: str
    provider_name: str
    confidence_level: str
    evidence_sha256: str
    sections: dict[str, str]
    raw_markdown: str
    source_path: Path


def load_executive_brief_artifact(
    path: str | Path | None = None,
) -> ExecutiveBriefArtifact:
    """Load the daily Brief with automatic cache invalidation on file changes."""

    candidate = (
        Path(path) if path is not None else get_dashboard_data_paths().executive_brief
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    resolved = candidate.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief artifact is not available."
        )
    try:
        stat = resolved.stat()
    except OSError as exc:
        raise ExecutiveBriefArtifactError(
            "Unable to inspect the automated Executive Brief artifact."
        ) from exc
    return _load_executive_brief_cached(
        str(resolved),
        stat.st_mtime_ns,
        stat.st_size,
    )


def clear_executive_brief_artifact_cache() -> None:
    """Clear the bounded artifact cache for tests and manual refreshes."""

    _load_executive_brief_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_executive_brief_cached(
    path_text: str,
    modified_at_ns: int,
    size: int,
) -> ExecutiveBriefArtifact:
    del modified_at_ns, size
    path = Path(path_text)
    try:
        markdown = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief is not readable UTF-8 Markdown."
        ) from exc
    return _parse_executive_brief_artifact(markdown, path)


def _parse_executive_brief_artifact(
    markdown: str,
    source_path: Path,
) -> ExecutiveBriefArtifact:
    sections = _artifact_sections(markdown)
    missing = tuple(name for name in _ARTIFACT_SECTIONS if not sections.get(name))
    if missing:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief is missing required sections: "
            + ", ".join(missing)
        )
    report_date_text = _metadata(markdown, "Report date")
    try:
        report_date = date.fromisoformat(report_date_text)
    except ValueError as exc:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief report date is invalid."
        ) from exc
    generated_text = _metadata(markdown, "Generated at")
    try:
        generated_at = datetime.fromisoformat(generated_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief generation timestamp is invalid."
        ) from exc
    if generated_at.tzinfo is None:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief generation timestamp needs a timezone."
        )
    evidence_sha256 = _metadata(markdown, "Evidence SHA-256").strip("`")
    if re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None:
        raise ExecutiveBriefArtifactError(
            "The automated Executive Brief evidence digest is invalid."
        )
    return ExecutiveBriefArtifact(
        report_date=report_date,
        generated_at=generated_at.astimezone(UTC),
        generation_mode=_metadata(markdown, "Generation mode"),
        provider_name=_metadata(markdown, "Provider"),
        confidence_level=_metadata(markdown, "Confidence"),
        evidence_sha256=evidence_sha256,
        sections=sections,
        raw_markdown=markdown,
        source_path=source_path,
    )


def _metadata(markdown: str, label: str) -> str:
    match = re.search(
        rf"^- {re.escape(label)}:\s*(.+?)\s*$",
        markdown,
        flags=re.MULTILINE,
    )
    if match is None or not match.group(1).strip():
        raise ExecutiveBriefArtifactError(
            f"The automated Executive Brief is missing {label}."
        )
    return match.group(1).strip()


def _artifact_sections(markdown: str) -> dict[str, str]:
    pattern = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    return {
        match.group(1): markdown[
            match.end() : (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(markdown)
            )
        ].strip()
        for index, match in enumerate(matches)
    }


class _BroadExecutiveExternalProvider:
    """Adapt the current provider to an executive-level cross-market query."""

    def __init__(
        self,
        provider: ExternalIntelligenceProvider,
    ) -> None:
        self._provider = provider

    @property
    def name(self) -> str:
        """Return the wrapped provider identifier."""

        return f"executive::{self._provider.name}"

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the wrapped provider capabilities unchanged."""

        return self._provider.capabilities

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Request broad verified signals while preserving the caller limit."""

        try:
            evidence = self._provider.search(
                ExternalQuery(
                    query="",
                    limit=max(query.limit, 64),
                )
            )
            filtered = tuple(
                item
                for item in evidence
                if item.category in _EXECUTIVE_EXTERNAL_CATEGORIES
            )
            return _select_executive_external_evidence(filtered, query.limit)
        except (OSError, ValueError, RuntimeError) as exc:
            raise IntelligenceProviderError(
                f"Executive external provider unavailable: {exc}"
            ) from exc


def build_executive_intelligence_brief(
    report: DailyMarketIntelligence | None,
    *,
    external_provider: ExternalIntelligenceProvider | None = None,
    llm_provider: AgentLLMProvider | None = None,
    generated_at: datetime | None = None,
) -> ExecutiveBrief:
    """Build the current brief without writing reports or database records."""

    if report is None or not report.vehicles:
        provider: ExternalIntelligenceProvider = EmptyExternalIntelligenceProvider()
    else:
        source = external_provider or build_default_external_provider()
        provider = _BroadExecutiveExternalProvider(source)
    evidence = retrieve_evidence(
        _BRIEF_QUESTION,
        report,
        external_provider=provider,
    )
    configured_llm = (
        llm_provider if llm_provider is not None else _configured_llm_provider()
    )
    return ExecutiveBriefGenerator(configured_llm).generate(
        evidence,
        generated_at=generated_at,
    )


def generate_executive_brief_artifact(
    report: DailyMarketIntelligence,
    *,
    output_path: str | Path | None = None,
    external_provider: ExternalIntelligenceProvider | None = None,
    llm_provider: AgentLLMProvider | None = None,
    generated_at: datetime | None = None,
) -> tuple[ExecutiveBrief, Path]:
    """Generate and atomically persist the standalone Markdown artifact."""

    brief = build_executive_intelligence_brief(
        report,
        external_provider=external_provider,
        llm_provider=llm_provider,
        generated_at=generated_at,
    )
    candidate = (
        Path(output_path) if output_path is not None else DEFAULT_EXECUTIVE_BRIEF_PATH
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return brief, write_executive_brief(brief, candidate)


def executive_brief_signature(report: DailyMarketIntelligence) -> str:
    """Return a bounded Dashboard cache key for current report inputs."""

    paths = get_dashboard_data_paths()
    payload = {
        "analytics": _file_signature(report.source_path),
        "content_feed": _file_signature(paths.content_feed),
        "external_intelligence": _file_signature(paths.external_intelligence),
        "report_date": report.report_date.isoformat(),
        "demo_mode": paths.demo_mode,
        "ai_provider": os.getenv("AI_PROVIDER", "local").strip().casefold(),
        "live_external": os.getenv("LIVE_EXTERNAL_INTELLIGENCE", "true")
        .strip()
        .casefold(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _select_executive_external_evidence(
    evidence: tuple[ExternalEvidence, ...],
    limit: int,
) -> tuple[ExternalEvidence, ...]:
    """Prefer category coverage before filling remaining newest evidence slots."""

    groups = (
        tuple(item for item in evidence if item.category == "policy_regulation"),
        tuple(item for item in evidence if item.category == "industry_report"),
        tuple(
            item
            for item in evidence
            if item.category == "brand_intelligence" or item.brand is not None
        ),
        tuple(
            item
            for item in evidence
            if item.category in {"news", "automotive_news"} and item.brand is None
        ),
    )
    selected: list[ExternalEvidence] = []
    seen: set[str] = set()
    for group in groups:
        for item in group[:2]:
            if item.url not in seen:
                selected.append(item)
                seen.add(item.url)
    for item in evidence:
        if len(selected) >= limit:
            break
        if item.url not in seen:
            selected.append(item)
            seen.add(item.url)
    return tuple(selected[:limit])
