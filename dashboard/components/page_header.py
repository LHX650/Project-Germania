"""Project and page header components."""

from __future__ import annotations

import html

import streamlit as st


def render_project_header(
    *,
    report_date: str | None = None,
    ai_generation_mode: str | None = None,
) -> None:
    """Render the dashboard's persistent project identity header."""

    status_badge = (
        '<span class="badge badge-connected">'
        f"Report · {html.escape(report_date)}"
        "</span>"
        if report_date is not None
        else '<span class="badge badge-pending">Analytics unavailable</span>'
    )
    ai_badge = (
        '<span class="badge badge-connected">'
        f"AI · {html.escape(ai_generation_mode)}"
        "</span>"
        if ai_generation_mode is not None
        else '<span class="badge badge-pending">AI report unavailable</span>'
    )
    st.markdown(
        f"""
        <header class="project-header">
            <div>
                <div class="project-eyebrow">GERMAN AUTOMOTIVE MARKET INTELLIGENCE</div>
                <h1>Project Germania</h1>
                <p>German Automotive Market Intelligence</p>
            </div>
            <div class="project-badges">
                <span class="badge badge-phase">Phase 12</span>
                {status_badge}
                {ai_badge}
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str) -> None:
    """Render a page title and concise descriptive subtitle."""

    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    st.markdown(
        f"""
        <section class="page-heading">
            <div class="page-kicker">INTELLIGENCE WORKSPACE</div>
            <h2>{safe_title}</h2>
            <p>{safe_subtitle}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    """Render the dashboard footer."""

    st.markdown(
        """
        <footer class="dashboard-footer">
            <span>Project Germania</span>
            <span>Phase 12 · Comparable Market Intelligence</span>
            <span>Read-only architecture</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )
