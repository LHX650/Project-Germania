"""Sidebar navigation for the Project Germania dashboard."""

from __future__ import annotations

import streamlit as st


EXECUTIVE_OVERVIEW = "Executive Overview"
MARKET_ANALYSIS = "Market Analysis"
VEHICLE_ANALYSIS = "Vehicle Analysis"
MARKET_MONITOR = "Market Monitor"
DATA_QUALITY = "Data Quality"
SEARCH_CENTER = "Search Center"

PAGE_NAMES: tuple[str, ...] = (
    EXECUTIVE_OVERVIEW,
    MARKET_ANALYSIS,
    VEHICLE_ANALYSIS,
    MARKET_MONITOR,
    DATA_QUALITY,
    SEARCH_CENTER,
)


def render_navigation() -> str:
    """Render the primary sidebar navigation and return the chosen page."""

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-mark">PG</div>
                <div>
                    <div class="sidebar-brand-name">Project Germania</div>
                    <div class="sidebar-brand-caption">Market Intelligence</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-section-label">Workspace</div>', unsafe_allow_html=True)
        selected_page = st.radio(
            "Dashboard pages",
            PAGE_NAMES,
            label_visibility="collapsed",
            key="project_germania_navigation",
        )
        st.markdown(
            """
            <div class="sidebar-status-card">
                <div class="sidebar-section-label">Environment</div>
                <div class="sidebar-status-row">
                    <span class="status-dot status-dot-amber"></span>
                    <span>Data connection pending</span>
                </div>
                <div class="sidebar-status-meta">Foundation release · Phase 17A</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return selected_page
