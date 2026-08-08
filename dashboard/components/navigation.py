"""Sidebar navigation for the Project Germania dashboard."""

from __future__ import annotations

import html

import streamlit as st

EXECUTIVE_OVERVIEW = "Executive Overview"
AI_MARKET_INSIGHTS = "AI Market Insights"
GLOBAL_INTELLIGENCE_HUB = "Global Intelligence"
MARKET_ALERTS = "Market Alerts"
VEHICLE_INTELLIGENCE = "Vehicle Intelligence"
BRAND_COMPETITION = "Brand Competition"
PRICE_INTELLIGENCE = "Price Intelligence"
MARKET_ANALYSIS = "Market Analysis"
VEHICLE_ANALYSIS = "Vehicle Analysis"
MARKET_MONITOR = "Market Monitor"
DATA_QUALITY = "Data Quality"
SEARCH_CENTER = "Listing Explorer"

PAGE_NAMES: tuple[str, ...] = (
    EXECUTIVE_OVERVIEW,
    MARKET_ALERTS,
    VEHICLE_INTELLIGENCE,
    BRAND_COMPETITION,
    PRICE_INTELLIGENCE,
    VEHICLE_ANALYSIS,
    GLOBAL_INTELLIGENCE_HUB,
    SEARCH_CENTER,
    DATA_QUALITY,
)

NAVIGATION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OVERVIEW", (EXECUTIVE_OVERVIEW, MARKET_ALERTS)),
    (
        "MARKET",
        (
            VEHICLE_INTELLIGENCE,
            BRAND_COMPETITION,
            PRICE_INTELLIGENCE,
        ),
    ),
    ("ANALYSIS", (VEHICLE_ANALYSIS, GLOBAL_INTELLIGENCE_HUB)),
    ("DATA", (SEARCH_CENTER, DATA_QUALITY)),
)

HIDDEN_PAGE_NAMES: tuple[str, ...] = (
    AI_MARKET_INSIGHTS,
    MARKET_MONITOR,
    MARKET_ANALYSIS,
)
ALL_PAGE_NAMES: tuple[str, ...] = (*PAGE_NAMES, *HIDDEN_PAGE_NAMES)
_NAVIGATION_KEY = "project_germania_navigation"
_GROUP_KEY_PREFIX = "project_germania_navigation_group_"


def render_navigation(
    *,
    report_date: str | None = None,
    ai_generation_mode: str | None = None,
) -> str:
    """Render the primary sidebar navigation and return the chosen page."""

    del ai_generation_mode

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
        selected_page = st.session_state.get(_NAVIGATION_KEY, EXECUTIVE_OVERVIEW)
        if selected_page not in ALL_PAGE_NAMES:
            selected_page = EXECUTIVE_OVERVIEW
        st.session_state[_NAVIGATION_KEY] = selected_page
        for group_index, (group_name, page_names) in enumerate(NAVIGATION_GROUPS):
            st.markdown(
                f'<div class="sidebar-section-label">{html.escape(group_name)}</div>',
                unsafe_allow_html=True,
            )
            group_key = f"{_GROUP_KEY_PREFIX}{group_index}"
            expected_value = selected_page if selected_page in page_names else None
            if st.session_state.get(group_key) != expected_value:
                st.session_state[group_key] = expected_value
            st.radio(
                group_name,
                page_names,
                index=None,
                label_visibility="collapsed",
                key=group_key,
                on_change=_select_group_page,
                args=(group_key,),
            )
        if report_date is None:
            status_dot = "status-dot-amber"
            status_text = "Market data unavailable"
            status_meta = "Read-only presentation layer"
        else:
            status_dot = "status-dot-green"
            status_text = "Market intelligence connected"
            status_meta = f"Data date · {html.escape(report_date)}"
        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-section-label">Environment</div>
                <div class="sidebar-status-row">
                    <span class="status-dot {status_dot}"></span>
                    <span>{status_text}</span>
                </div>
                <div class="sidebar-status-meta">{status_meta}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return selected_page


def _select_group_page(group_key: str) -> None:
    """Persist one visible page while retaining hidden legacy fallback routes."""

    selected_page = st.session_state.get(group_key)
    if selected_page in PAGE_NAMES:
        st.session_state[_NAVIGATION_KEY] = selected_page
