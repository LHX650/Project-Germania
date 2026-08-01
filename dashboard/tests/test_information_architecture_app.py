"""Streamlit AppTest coverage for the eight-page information architecture."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]


def test_grouped_navigation_and_page_switching_are_stable() -> None:
    app = AppTest.from_string(_app_source(), default_timeout=10).run()

    assert not app.exception
    assert [radio.options for radio in app.radio] == [
        ["Executive Overview"],
        [
            "Global Automotive Intelligence Hub",
            "Vehicle Intelligence",
            "Brand Competition",
            "Price Intelligence",
        ],
        ["Vehicle Analysis", "Search Center"],
        ["Data Quality"],
    ]
    assert _has_page_heading(app, "Executive Overview")
    assert "Pipeline Status" in [item.value for item in app.subheader]
    assert "AI Summary" in [item.value for item in app.subheader]

    app.radio[2].set_value("Vehicle Analysis").run()
    assert not app.exception
    assert _has_page_heading(app, "Vehicle Analysis")

    app.radio[0].set_value("Executive Overview").run()
    assert not app.exception
    assert _has_page_heading(app, "Executive Overview")

    app.radio[3].set_value("Data Quality").run()
    assert not app.exception
    assert _has_page_heading(app, "Data Quality")


def test_hidden_ai_page_remains_available_as_an_internal_fallback() -> None:
    app = AppTest.from_string(_hidden_page_source(), default_timeout=10).run()

    assert not app.exception
    assert _has_page_heading(app, "AI Market Insights")
    assert all("AI Market Insights" not in radio.options for radio in app.radio)


def _app_source() -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
import app
app._load_report = lambda: (None, "analytics fixture unavailable")
app._load_ai_report = lambda: (None, "ai fixture unavailable")
app._load_pipeline_status = lambda: (None, "pipeline fixture unavailable")
app.main()
"""


def _hidden_page_source() -> str:
    return f"""
import sys
sys.path.insert(0, {str(DASHBOARD_DIR)!r})
import streamlit as st
import app
st.session_state["project_germania_navigation"] = "AI Market Insights"
app._load_report = lambda: (None, "analytics fixture unavailable")
app._load_ai_report = lambda: (None, "ai fixture unavailable")
app._load_pipeline_status = lambda: (None, "pipeline fixture unavailable")
app.main()
"""


def _has_page_heading(app: AppTest, page_name: str) -> bool:
    return any(page_name in str(item.value) for item in app.markdown)
