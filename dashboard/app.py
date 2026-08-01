"""Single Streamlit entry point for the Project Germania dashboard."""

# ruff: noqa: E402 -- the standalone entry point adds dashboard/ before imports.

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
PROJECT_ROOT = DASHBOARD_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
from components.navigation import (
    AI_MARKET_INSIGHTS,
    BRAND_COMPETITION,
    DATA_QUALITY,
    EXECUTIVE_OVERVIEW,
    GLOBAL_INTELLIGENCE_HUB,
    MARKET_ANALYSIS,
    MARKET_MONITOR,
    PRICE_INTELLIGENCE,
    SEARCH_CENTER,
    VEHICLE_ANALYSIS,
    VEHICLE_INTELLIGENCE,
    render_navigation,
)
from components.page_header import render_footer, render_project_header
from pages.ai_market_insights import render as render_ai_market_insights
from pages.brand_competition import render as render_brand_competition
from pages.data_quality import render as render_data_quality
from pages.executive_overview import render as render_executive_overview
from pages.global_intelligence_hub import render as render_global_intelligence_hub
from pages.market_analysis import render as render_market_analysis
from pages.market_monitor import render as render_market_monitor
from pages.price_intelligence import render as render_price_intelligence
from pages.search_center import render as render_search_center
from pages.vehicle_analysis import render as render_vehicle_analysis
from pages.vehicle_intelligence import render as render_vehicle_intelligence
from services.ai_report import (
    AIMarketReport,
    AIReportError,
    load_daily_ai_market_report,
)
from services.intelligence import (
    DailyMarketIntelligence,
    IntelligenceReportError,
    load_daily_market_intelligence,
)
from services.pipeline_status import (
    PipelineStatus,
    PipelineStatusError,
    load_pipeline_status,
)
from services.runtime import demo_mode_enabled
from theme.styles import apply_global_styles

STATIC_PAGE_RENDERERS: dict[str, Callable[[], None]] = {
    MARKET_ANALYSIS: render_market_analysis,
    MARKET_MONITOR: render_market_monitor,
    SEARCH_CENTER: render_search_center,
}
INTELLIGENCE_PAGE_RENDERERS: dict[
    str,
    Callable[[DailyMarketIntelligence | None, str | None], None],
] = {
    VEHICLE_INTELLIGENCE: render_vehicle_intelligence,
    BRAND_COMPETITION: render_brand_competition,
    PRICE_INTELLIGENCE: render_price_intelligence,
    VEHICLE_ANALYSIS: render_vehicle_analysis,
}
AI_PAGE_RENDERERS: dict[
    str,
    Callable[[AIMarketReport | None, str | None], None],
] = {
    AI_MARKET_INSIGHTS: render_ai_market_insights,
}
CONTENT_PAGE_RENDERERS: dict[
    str,
    Callable[[DailyMarketIntelligence | None], None],
] = {
    GLOBAL_INTELLIGENCE_HUB: render_global_intelligence_hub,
}


def main() -> None:
    """Configure and render the read-only Phase 10 intelligence Dashboard."""

    st.set_page_config(
        page_title="Project Germania | Market Intelligence",
        page_icon="🚘",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_global_styles()

    report, report_error = _load_report()
    ai_report, ai_report_error = _load_ai_report()
    pipeline, pipeline_error = _load_pipeline_status()
    report_date = report.report_date.isoformat() if report is not None else None
    ai_generation_mode = ai_report.generation_mode if ai_report is not None else None
    selected_page = render_navigation(
        report_date=report_date,
        ai_generation_mode=ai_generation_mode,
    )
    render_project_header(
        report_date=report_date,
        ai_generation_mode=ai_generation_mode,
    )
    if demo_mode_enabled():
        st.info(
            "Demo Mode — this interface uses public, synthetic, anonymized, "
            "read-only sample data. Listing counts and asking prices are "
            "provided for product demonstration only and do not represent "
            "current market facts.",
            icon=":material/science:",
        )
    ai_renderer = AI_PAGE_RENDERERS.get(selected_page)
    content_renderer = CONTENT_PAGE_RENDERERS.get(selected_page)
    intelligence_renderer = INTELLIGENCE_PAGE_RENDERERS.get(selected_page)
    if selected_page == EXECUTIVE_OVERVIEW:
        render_executive_overview(
            report,
            report_error,
            ai_report=ai_report,
            ai_error=ai_report_error,
            pipeline=pipeline,
            pipeline_error=pipeline_error,
        )
    elif selected_page == DATA_QUALITY:
        render_data_quality(pipeline, pipeline_error)
    elif content_renderer is not None:
        content_renderer(report)
    elif ai_renderer is not None:
        ai_renderer(ai_report, ai_report_error)
    elif intelligence_renderer is not None:
        intelligence_renderer(report, report_error)
    else:
        STATIC_PAGE_RENDERERS[selected_page]()
    render_footer()


def _load_report() -> tuple[DailyMarketIntelligence | None, str | None]:
    try:
        return load_daily_market_intelligence(), None
    except IntelligenceReportError as exc:
        return None, str(exc)


def _load_ai_report() -> tuple[AIMarketReport | None, str | None]:
    try:
        return load_daily_ai_market_report(), None
    except AIReportError as exc:
        return None, str(exc)


def _load_pipeline_status() -> tuple[PipelineStatus | None, str | None]:
    try:
        return load_pipeline_status(), None
    except PipelineStatusError as exc:
        return None, str(exc)


if __name__ == "__main__":
    main()
