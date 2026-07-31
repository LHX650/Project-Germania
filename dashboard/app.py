"""Single Streamlit entry point for the Project Germania dashboard."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys


DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import streamlit as st

from components.navigation import (
    DATA_QUALITY,
    EXECUTIVE_OVERVIEW,
    MARKET_ANALYSIS,
    MARKET_MONITOR,
    SEARCH_CENTER,
    VEHICLE_ANALYSIS,
    render_navigation,
)
from components.page_header import render_footer, render_project_header
from pages.data_quality import render as render_data_quality
from pages.executive_overview import render as render_executive_overview
from pages.market_analysis import render as render_market_analysis
from pages.market_monitor import render as render_market_monitor
from pages.search_center import render as render_search_center
from pages.vehicle_analysis import render as render_vehicle_analysis
from theme.styles import apply_global_styles


PAGE_RENDERERS: dict[str, Callable[[], None]] = {
    EXECUTIVE_OVERVIEW: render_executive_overview,
    MARKET_ANALYSIS: render_market_analysis,
    VEHICLE_ANALYSIS: render_vehicle_analysis,
    MARKET_MONITOR: render_market_monitor,
    DATA_QUALITY: render_data_quality,
    SEARCH_CENTER: render_search_center,
}


def main() -> None:
    """Configure and render the Phase 17A dashboard shell."""

    st.set_page_config(
        page_title="Project Germania | Market Intelligence",
        page_icon="🚘",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_global_styles()

    selected_page = render_navigation()
    render_project_header()
    PAGE_RENDERERS[selected_page]()
    render_footer()


if __name__ == "__main__":
    main()
