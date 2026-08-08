from __future__ import annotations

from pathlib import Path

import pytest
from services.ai_agent import (
    _configured_llm_provider,
    answer_question,
    retrieve_evidence,
)
from services.intelligence import load_daily_market_intelligence
from streamlit.testing.v1 import AppTest

from ai.intelligence.agent import NO_EVIDENCE_MESSAGE
from ai.intelligence.api_providers import ClaudeProvider, GeminiProvider, OpenAIProvider
from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import EmptyExternalIntelligenceProvider, ExternalQuery

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_DIR.parent
PRODUCTION_ARTIFACTS_AVAILABLE = (
    PROJECT_ROOT / "reports" / "daily_market_intelligence.json"
).is_file() and (PROJECT_ROOT / "database" / "project_germania_live.sqlite3").is_file()


def test_demo_mode_retrieves_internal_evidence_without_external_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "local")
    report = load_daily_market_intelligence()

    evidence = retrieve_evidence(
        "Which vehicles have the highest opportunity?",
        report,
        external_provider=EmptyExternalIntelligenceProvider(),
    )
    answer = answer_question(
        "Which vehicles have the highest opportunity?",
        report,
        external_provider=EmptyExternalIntelligenceProvider(),
    )

    assert evidence.analytics_date == report.report_date.isoformat()
    assert evidence.vehicles
    assert not evidence.external
    assert any(
        "external intelligence" in item.casefold() for item in evidence.data_gaps
    )
    assert evidence.external_status == "insufficient_data"
    assert answer.confidence_level.startswith(("High", "Medium"))
    assert "Vehicle Opportunity Score" in answer.to_markdown()
    assert any(
        item.metric_name == "External Evidence Status"
        and item.value == "insufficient_data"
        for item in answer.evidence_records
    )


def test_mock_external_provider_is_retrieved_and_cited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    report = load_daily_market_intelligence()
    provider = _MockExternalProvider()

    evidence = retrieve_evidence(
        "What are the main market risks?",
        report,
        external_provider=provider,
    )
    answer = answer_question(
        "What are the main market risks?",
        report,
        external_provider=provider,
    )

    assert evidence.external_status == "available"
    assert evidence.external[0].source == "Official Association"
    assert "https://example.org/report" in answer.to_markdown()
    assert "Internal Data Evidence" in answer.to_markdown()
    assert "External Market Signal" in answer.to_markdown()
    assert any(
        item.evidence_source == "External Market Signals · Official Association"
        for item in answer.evidence_records
    )


def test_unverified_external_provider_data_is_excluded_from_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    report = load_daily_market_intelligence()

    evidence = retrieve_evidence(
        "What are the main market risks?",
        report,
        external_provider=_UnverifiedExternalProvider(),
    )

    assert evidence.external == ()
    assert evidence.external_status == "insufficient_data"


@pytest.mark.skipif(
    not PRODUCTION_ARTIFACTS_AVAILABLE,
    reason="production read-only artifacts are not present",
)
def test_production_mode_retrieves_current_read_only_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LIVE_EXTERNAL_INTELLIGENCE", "false")
    monkeypatch.setenv("AI_PROVIDER", "local")
    report = load_daily_market_intelligence()

    evidence = retrieve_evidence("Why is Tesla Model Y under pressure?", report)
    answer = answer_question("Why is Tesla Model Y under pressure?", report)

    assert evidence.analytics_date == report.report_date.isoformat()
    assert evidence.vehicles
    assert answer.generation_mode == "local_rules"
    assert "Tesla Model Y" in answer.to_markdown()


def test_no_analytics_data_returns_explicit_insufficient_answer() -> None:
    answer = answer_question(
        "What are the risks?",
        None,
        external_provider=EmptyExternalIntelligenceProvider(),
    )

    assert answer.situation_summary == NO_EVIDENCE_MESSAGE
    assert answer.confidence_level == "Insufficient"


def test_configured_unavailable_llm_adapter_falls_back_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = load_daily_market_intelligence()

    answer = answer_question(
        "What are the main risks?",
        report,
        external_provider=EmptyExternalIntelligenceProvider(),
    )

    assert answer.generation_mode == "local_rules_fallback"
    assert answer.provider_name == "openai"
    assert answer.evidence


@pytest.mark.parametrize(
    ("name", "provider_type"),
    (
        ("openai", OpenAIProvider),
        ("claude", ClaudeProvider),
        ("anthropic", ClaudeProvider),
        ("gemini", GeminiProvider),
        ("google", GeminiProvider),
    ),
)
def test_configured_provider_name_selects_concrete_adapter(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    provider_type: type[OpenAIProvider | ClaudeProvider | GeminiProvider],
) -> None:
    monkeypatch.setenv("AI_PROVIDER", name)

    assert isinstance(_configured_llm_provider(), provider_type)


def test_executive_embeds_one_brief_and_on_demand_market_analyst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_string(
        _app_source("Executive Overview"), default_timeout=30
    ).run()

    assert not app.exception
    assert "Executive Brief" in {item.value for item in app.subheader}
    assert "Market Intelligence Analyst" in {item.value for item in app.subheader}
    assert {"Today's brief", "Top risks", "Top opportunities"} <= {
        str(item.value).strip("*") for item in app.markdown
    }
    suggested_labels = {item.label for item in app.button}
    assert "Which vehicles have the highest opportunity?" in suggested_labels
    assert "What are the main market risks?" in suggested_labels

    app.text_input[0].set_value("Which vehicles have the highest opportunity?")
    app.button(
        key=(
            "FormSubmitter:ai_automotive_intelligence_question-"
            "Analyze current evidence"
        )
    ).click().run()
    assert not app.exception
    assert any("Situation Summary" in str(item.value) for item in app.markdown)
    assert any("Supporting evidence" in str(item.value) for item in app.markdown)
    evidence_columns = {
        "Evidence Source",
        "Metric Name",
        "Value",
        "Timestamp",
    }
    assert any(evidence_columns <= set(frame.value.columns) for frame in app.dataframe)


def test_vehicle_and_alert_actions_render_grounded_explanations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    vehicle_app = AppTest.from_string(
        _app_source("Vehicle Analysis"), default_timeout=30
    ).run()
    analysis_button = next(
        item for item in vehicle_app.button if item.label == "Generate Analysis"
    )
    analysis_button.click().run()

    assert not vehicle_app.exception
    assert {
        "1. Market Position",
        "2. Competitive Strength",
        "3. Key Risks",
        "4. Peer Comparison",
        "5. Recommended Monitoring",
    } <= {str(item.value).strip("*") for item in vehicle_app.markdown}
    assert {
        "Vehicle Opportunity Score",
        "Price Pressure Index",
        "Inventory Pressure Index",
        "Peer Status",
    } <= {item.label for item in vehicle_app.metric}
    assert any(
        "Supporting evidence" in str(item.value) for item in vehicle_app.markdown
    )

    alert_app = AppTest.from_string(
        _app_source("Market Alerts"), default_timeout=30
    ).run()
    assert "Alert explanation" in {item.value for item in alert_app.subheader}
    alert_app.button(key="generate_ai_alert_explanation").click().run()

    assert not alert_app.exception
    assert {
        "Alert Reason",
        "Supporting Evidence",
        "Competitive Impact",
        "Recommended Action",
    } <= {str(item.value).strip("*") for item in alert_app.markdown}
    assert any("Supporting evidence" in str(item.value) for item in alert_app.markdown)


def _app_source(page_name: str) -> str:
    return f"""
import os
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = "true"
import streamlit as st
st.session_state["project_germania_navigation"] = {page_name!r}
import app
app.main()
"""


class _MockExternalProvider:
    name = "mock_external"
    capabilities = frozenset({"industry_report"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        return (
            ExternalEvidence(
                source="Official Association",
                title="German automotive market report",
                url="https://example.org/report",
                published_date="2026-08-07",
                category="industry_report",
                brand=None,
                vehicle=None,
                content_summary="Attributed report metadata.",
                reliability=90,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="official_industry_report",
                region="EU",
            ),
        )


class _UnverifiedExternalProvider:
    name = "unverified_external"
    capabilities = frozenset({"news"})

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        del query
        return (
            ExternalEvidence(
                source="Unknown source",
                title="Unverified claim",
                url="https://example.org/unverified",
                published_date="2026-08-07",
                category="automotive_news",
                brand=None,
                vehicle=None,
                content_summary="Unverified content.",
                reliability=20,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="unverified",
                region="EU",
            ),
        )
