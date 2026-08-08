from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_demo_market_alerts_page_renders_summary_rankings_and_trend_notice(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_string(_demo_source(), default_timeout=20).run()

    assert not app.exception
    assert _has_heading(app, "Market Alerts")
    assert {item.value for item in app.subheader} >= {
        "Alert Summary",
        "Alert Ranking",
        "Vehicle Risk Ranking",
        "Historical Alert Trend",
    }
    assert {item.label for item in app.metric} >= {
        "Critical",
        "Warning",
        "Normal",
        "Insufficient data",
        "Vehicles monitored",
    }
    assert len(app.dataframe) >= 2
    assert any("insufficient_data" in str(item.value) for item in app.info)


def test_empty_market_alerts_page_is_explicit_and_error_free() -> None:
    app = AppTest.from_string(_empty_source(), default_timeout=20).run()

    assert not app.exception
    assert _has_heading(app, "Market Alerts")
    assert any(
        "current Analytics report has no vehicles" in str(item.value)
        for item in app.info
    )


def _demo_source() -> str:
    return f"""
import os
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
os.environ["DEMO_MODE"] = "true"
import streamlit as st
st.session_state["project_germania_navigation"] = "Market Alerts"
import app
from services.intelligence import load_daily_market_intelligence
app._load_report = lambda: (load_daily_market_intelligence(), None)
app.main()
"""


def _empty_source() -> str:
    return f"""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
import streamlit as st
from services.intelligence import DailyMarketIntelligence
st.session_state["project_germania_navigation"] = "Market Alerts"
import app
app._load_report = lambda: (
    DailyMarketIntelligence(
        report_date=date(2026, 8, 7),
        vehicles=(),
        brands=(),
        methodology={{}},
        quantitative_scores=(),
        source_path=Path("empty.json"),
    ),
    None,
)
app._load_ai_report = lambda: (None, "AI fixture unavailable")
app._load_pipeline_status = lambda: (None, "Pipeline fixture unavailable")
app.main()
"""


def _has_heading(app: AppTest, title: str) -> bool:
    return any(title in str(item.value) for item in app.markdown)
