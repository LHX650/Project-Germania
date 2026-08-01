"""Shared placeholder content for Phase 17A pages."""

from __future__ import annotations

import html
from collections.abc import Sequence

import streamlit as st


def render_phase_placeholder(
    *,
    page_name: str,
    description: str,
    planned_items: Sequence[str],
) -> None:
    """Render a consistent no-data placeholder for one dashboard page."""

    st.markdown(
        f"""
        <section class="foundation-panel">
            <div class="foundation-icon">17A</div>
            <div>
                <div class="foundation-label">DASHBOARD FOUNDATION</div>
                <h3>{html.escape(page_name)} framework is ready</h3>
                <p>{html.escape(description)}</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    columns = st.columns(len(planned_items))
    for column, item in zip(columns, planned_items, strict=True):
        with column:
            st.markdown(
                f"""
                <div class="planned-card">
                    <div class="planned-card-label">PLANNED VIEW</div>
                    <div class="planned-card-title">{html.escape(item)}</div>
                    <div class="planned-card-meta">
                        Awaiting the Phase 17B data layer
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.info(
        "Phase 17A contains no simulated data and performs no database queries. "
        "Real SQLite data will be connected in the next phase. "
        "Live data will be connected in a future phase.",
        icon="ℹ️",
    )
