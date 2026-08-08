from __future__ import annotations

from pathlib import Path

import pytest
from services.executive_brief import (
    build_executive_intelligence_brief,
    clear_executive_brief_artifact_cache,
    generate_executive_brief_artifact,
    load_executive_brief_artifact,
)
from services.intelligence import load_daily_market_intelligence
from services.runtime import get_dashboard_data_paths
from streamlit.testing.v1 import AppTest

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import ExternalQuery

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_DIR.parent
PRODUCTION_ARTIFACTS_AVAILABLE = (
    PROJECT_ROOT / "reports" / "daily_market_intelligence.json"
).is_file() and (PROJECT_ROOT / "database" / "project_germania_live.sqlite3").is_file()


def test_demo_brief_uses_read_only_internal_and_external_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    paths = get_dashboard_data_paths()
    database_stat = paths.database.stat()
    report = load_daily_market_intelligence()

    brief, output = generate_executive_brief_artifact(
        report,
        output_path=tmp_path / "brief.md",
        external_provider=_ExternalProvider(),
    )

    assert brief.report_date == report.report_date.isoformat()
    assert brief.internal_evidence
    assert brief.external_evidence
    assert len(brief.external_evidence) == 1
    assert brief.external_evidence[0].source == "Official Policy Source"
    assert output.is_file()
    assert "## Executive Summary" in output.read_text(encoding="utf-8")
    current_database_stat = paths.database.stat()
    assert current_database_stat.st_size == database_stat.st_size
    assert current_database_stat.st_mtime_ns == database_stat.st_mtime_ns


def test_external_provider_failure_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    report = load_daily_market_intelligence()

    brief = build_executive_intelligence_brief(
        report,
        external_provider=_FailedExternalProvider(),
    )

    assert brief.internal_evidence
    assert not brief.external_evidence
    assert brief.external_news_policy_signals == ("insufficient_data",)
    assert any("External intelligence unavailable" in gap for gap in brief.data_gaps)


def test_empty_report_returns_insufficient_data_without_external_call() -> None:
    provider = _CountingExternalProvider()

    brief = build_executive_intelligence_brief(None, external_provider=provider)

    assert brief.executive_summary == "insufficient_data"
    assert provider.calls == 0


@pytest.mark.skipif(
    not PRODUCTION_ARTIFACTS_AVAILABLE,
    reason="production read-only artifacts are not present",
)
def test_production_brief_reads_current_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LIVE_EXTERNAL_INTELLIGENCE", "false")
    monkeypatch.setenv("AI_PROVIDER", "local")
    report = load_daily_market_intelligence()

    brief = build_executive_intelligence_brief(report)

    assert brief.report_date == report.report_date.isoformat()
    assert brief.internal_evidence
    assert brief.evidence_sha256


def test_executive_overview_renders_brief_cards_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    app = AppTest.from_string(_app_source(), default_timeout=30).run()

    assert not app.exception
    assert "Executive Intelligence Brief" in {item.value for item in app.subheader}
    labels = {str(item.value).strip("*") for item in app.markdown}
    assert {"Today's Brief", "Risk Summary", "Opportunity Summary"} <= labels
    assert {item.label for item in app.expander} >= {"Brief sections", "Evidence"}
    evidence = next(item for item in app.expander if item.label == "Evidence")
    assert any(
        "Internal Market Evidence" in str(item.value) for item in evidence.markdown
    )
    assert any(
        "External Market Signals" in str(item.value) for item in evidence.markdown
    )


def test_automated_artifact_loader_refreshes_after_file_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "daily_executive_intelligence_brief.md"
    path.write_text(
        _artifact_markdown("2026-07-30", "First summary."), encoding="utf-8"
    )

    first = load_executive_brief_artifact(path)
    path.write_text(
        _artifact_markdown("2026-07-31", "Updated and longer summary."),
        encoding="utf-8",
    )
    second = load_executive_brief_artifact(path)

    assert first.report_date.isoformat() == "2026-07-30"
    assert second.report_date.isoformat() == "2026-07-31"
    assert second.sections["Executive Summary"] == "Updated and longer summary."
    assert first is not second


def test_dashboard_renders_preserved_brief_and_declared_data_date(
    tmp_path: Path,
) -> None:
    path = tmp_path / "daily_executive_intelligence_brief.md"
    path.write_text(
        _artifact_markdown("2026-07-30", "Preserved valid summary."),
        encoding="utf-8",
    )
    source = f"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = "true"
import services.executive_brief as executive_service
executive_service.get_dashboard_data_paths = lambda: SimpleNamespace(
    executive_brief=Path({str(path)!r})
)
from components.executive_brief import render_executive_intelligence_brief
from services.intelligence import load_daily_market_intelligence
render_executive_intelligence_brief(load_daily_market_intelligence())
"""

    app = AppTest.from_string(source, default_timeout=30).run()

    assert not app.exception
    assert any("Preserved valid summary." in str(item.value) for item in app.markdown)
    assert any("2026-07-30" in str(item.value) for item in app.caption)
    assert any("latest valid Executive Brief" in item.value for item in app.warning)


def _app_source() -> str:
    return f"""
import os
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = "true"
os.environ["AI_PROVIDER"] = "local"
import streamlit as st
st.session_state["project_germania_navigation"] = "Executive Overview"
import app
app.main()
"""


class _ExternalProvider:
    name = "official_policy_mock"
    capabilities = frozenset({"policy_regulation"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        return (
            ExternalEvidence(
                source="Official Policy Source",
                title="German automotive policy update",
                url="https://example.org/policy",
                published_date="2026-08-07",
                category="policy_regulation",
                brand=None,
                vehicle=None,
                content_summary="Official policy metadata.",
                reliability=95,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="official_policy",
                region="DE",
            ),
            ExternalEvidence(
                source="Public Video Channel",
                title="Automotive video",
                url="https://example.org/video",
                published_date="2026-08-07",
                category="search",
                brand=None,
                vehicle=None,
                content_summary="Public video metadata.",
                reliability=85,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="validated_public_video",
                region="GLOBAL",
            ),
        )


class _FailedExternalProvider:
    name = "failed"
    capabilities = frozenset({"news"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        raise RuntimeError("provider unavailable")


class _CountingExternalProvider:
    name = "counting"
    capabilities = frozenset({"news"})

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        self.calls += 1
        return ()


@pytest.fixture(autouse=True)
def _clear_artifact_cache() -> None:
    clear_executive_brief_artifact_cache()


def _artifact_markdown(report_date: str, summary: str) -> str:
    sections = {
        "Executive Summary": summary,
        "Top Market Changes": "- Change grounded in evidence.",
        "Critical Risks": "- Risk grounded in evidence.",
        "Top Opportunities": "- Opportunity grounded in evidence.",
        "Competitive Movements": "- Peer movement grounded in evidence.",
        "External News & Policy Signals": "- External signal.",
        "Recommended Monitoring Actions": "- Monitor the next update.",
        "Internal Market Evidence": (
            "| Metric | Value |\n| --- | ---: |\n| Score | 50 |"
        ),
        "External Market Signals": (
            "| Source | Evidence |\n| --- | --- |\n| Official | Signal |"
        ),
        "Data Coverage": "- No disclosed data gaps.",
    }
    body = "\n\n".join(f"## {name}\n\n{value}" for name, value in sections.items())
    return (
        "# Germany Automotive Executive Brief\n\n"
        f"- Report date: {report_date}\n"
        "- Generated at: 2026-08-08T00:00:00+00:00\n"
        "- Generation mode: local_rules\n"
        "- Provider: local_rules\n"
        "- Confidence: Medium\n"
        f"- Evidence SHA-256: `{'a' * 64}`\n\n"
        f"{body}\n"
    )
