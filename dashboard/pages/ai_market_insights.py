"""AI Market Insights page backed by the generated Markdown report."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
from components.page_header import render_page_header
from services.ai_report import AIMarketReport


def render(
    report: AIMarketReport | None,
    error_message: str | None = None,
) -> None:
    """Render dynamic AI insights without database or collection access."""

    render_page_header(
        title="AI Market Insights",
        subtitle=(
            "German automotive market summary, opportunities, and risks from the "
            "daily AI Market Report."
        ),
    )
    if report is None:
        _render_unavailable(error_message)
        return

    _render_metadata(report)

    with st.container(border=True):
        st.subheader("Latest AI market summary")
        st.markdown(report.market_overview_markdown)

    opportunity_column, risk_column = st.columns(2)
    with opportunity_column, st.container(border=True):
        st.subheader("Market opportunities")
        st.markdown(report.market_opportunity_markdown)
    with risk_column, st.container(border=True):
        st.subheader("Risk alerts")
        st.markdown(report.risk_markdown)

    with st.container(border=True):
        st.subheader("Priority vehicle analysis")
        st.markdown(report.vehicle_opportunity_markdown)

    with st.expander("View full AI Market Report"):
        st.markdown(report.raw_markdown)

    st.caption(
        "AI interpretation comes from a read-only Markdown report. Asking prices "
        "are not transaction prices, and listing inventory does not represent "
        "sales or new vehicle registrations."
    )


def _render_metadata(report: AIMarketReport) -> None:
    generated_at = _berlin_time(report)
    provider = report.provider_name or "Local rules-based analysis"
    with st.container(horizontal=True):
        st.metric("Analytics data date", report.analytics_date.isoformat(), border=True)
        st.metric("Report generated at", generated_at, border=True)
        st.metric("Generation mode", report.generation_mode, border=True)
        st.metric("LLM Provider", provider, border=True)
    st.caption(
        f"Source: {report.source_path.name} · Report generation time is derived "
        "from the Markdown file's last-modified timestamp (Europe/Berlin)."
    )


def _berlin_time(report: AIMarketReport) -> str:
    try:
        timezone = ZoneInfo("Europe/Berlin")
        suffix = "CEST" if report.generated_at_utc.astimezone(timezone).dst() else "CET"
    except ZoneInfoNotFoundError:
        timezone = report.generated_at_utc.tzinfo
        suffix = "UTC"
    return report.generated_at_utc.astimezone(timezone).strftime(
        f"%Y-%m-%d %H:%M {suffix}"
    )


def _render_unavailable(message: str | None) -> None:
    st.error(
        message
        or "The AI market report is unavailable. Generate the daily AI Market "
        "Report before opening this page.",
        icon=":material/error:",
    )
    st.code(
        ".\\.venv\\Scripts\\python.exe -m ai "
        "--input reports\\daily_market_intelligence.json "
        "--output reports\\daily_ai_market_report.md",
        language="powershell",
    )
