"""Project and page header components."""

from __future__ import annotations

import html

import streamlit as st


def render_project_header() -> None:
    """Render the dashboard's persistent project identity header."""

    st.markdown(
        """
        <header class="project-header">
            <div>
                <div class="project-eyebrow">GERMAN AUTOMOTIVE MARKET INTELLIGENCE</div>
                <h1>Project Germania</h1>
                <p>German Automotive Market Intelligence</p>
            </div>
            <div class="project-badges">
                <span class="badge badge-phase">Phase 17A</span>
                <span class="badge badge-pending">Data connection pending</span>
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
            <span>Phase 17A · Dashboard Foundation</span>
            <span>Read-only architecture</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )
