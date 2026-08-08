"""Brand Competition page powered by Phase 5A analytics output."""

from __future__ import annotations

import sqlite3

import streamlit as st
from components.intelligence import (
    format_eur,
    format_percentage,
    render_intelligence_unavailable,
    render_report_notice,
)
from components.page_header import render_page_header
from components.peer_benchmarking import peer_overview_rows
from services.intelligence import DailyMarketIntelligence, vehicle_key
from services.peer_benchmarking import load_peer_benchmarks


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
) -> None:
    """Render active inventory, electrification, and model coverage by brand."""

    render_page_header(
        title="Brand Competition",
        subtitle=(
            "Compare brand inventory, average asking prices, electrified "
            "powertrain mix, and model coverage."
        ),
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.brands:
        st.info("The current report contains no brand records.")
        return

    ranked = sorted(
        report.brands,
        key=lambda item: (
            item.metrics.active_inventory_rank,
            item.brand.casefold(),
        ),
    )
    selected_brand = st.selectbox("Focus brand", [item.brand for item in ranked])
    selected = next(item for item in ranked if item.brand == selected_brand)
    metrics = selected.metrics
    with st.container(horizontal=True):
        st.metric("Inventory rank", f"#{metrics.active_inventory_rank}", border=True)
        st.metric(
            "Active inventory", f"{metrics.active_inventory_count:,}", border=True
        )
        st.metric(
            "Average asking price",
            format_eur(metrics.average_vehicle_price_eur),
            border=True,
        )
        st.metric(
            "BEV + PHEV share",
            format_percentage(metrics.bev_phev_share_pct),
            border=True,
        )
        st.metric(
            "Model coverage",
            format_percentage(metrics.model_coverage_pct),
            border=True,
        )

    chart_rows = [
        {
            "Brand": item.brand,
            "Active inventory": item.metrics.active_inventory_count,
        }
        for item in ranked
    ]
    st.subheader("Brand inventory landscape")
    with st.container(border=True):
        st.bar_chart(
            chart_rows,
            x="Brand",
            y="Active inventory",
            color="#376f93",
            height=360,
        )

    rows = [
        {
            "Rank": item.metrics.active_inventory_rank,
            "Brand": item.brand,
            "Active inventory": item.metrics.active_inventory_count,
            "Average asking price (EUR)": item.metrics.average_vehicle_price_eur,
            "BEV share (%)": item.metrics.bev_share_pct,
            "PHEV share (%)": item.metrics.phev_share_pct,
            "BEV + PHEV share (%)": item.metrics.bev_phev_share_pct,
            "Model coverage": (
                f"{item.metrics.model_coverage_count}/"
                f"{item.metrics.catalog_model_count}"
            ),
            "Coverage (%)": item.metrics.model_coverage_pct,
        }
        for item in ranked
    ]
    with st.expander("Brand metric details"):
        st.dataframe(rows, hide_index=True, width="stretch", height=470)
    with st.expander("Comparable vehicle positioning"):
        _render_brand_peer_view(report, selected_brand)


def _render_brand_peer_view(
    report: DailyMarketIntelligence,
    selected_brand: str,
) -> None:
    st.markdown("**Brand vehicle peer benchmarks**")
    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.info(
            "insufficient_data: comparable-vehicle controls are unavailable. "
            f"Reason: {exc}"
        )
        return
    keys = {
        vehicle_key(item.brand, item.model)
        for item in report.vehicles
        if item.brand == selected_brand
    }
    rows = peer_overview_rows(peer_report, vehicle_keys=keys)
    if not rows:
        st.info("insufficient_data: this brand has no Analytics vehicle records.")
        return
    comparable = [
        row
        for row in rows
        if row["Status"] == "ok" and row["Opportunity Score Gap"] is not None
    ]
    if comparable:
        with st.container(border=True):
            st.bar_chart(
                comparable,
                x="Vehicle",
                y="Opportunity Score Gap",
                color="#376f93",
                height=300,
            )
        st.caption(
            "Each vehicle is compared with its own dynamic Peer Group; vehicles "
            "from different segments are not combined into one broad benchmark."
        )
    st.dataframe(rows, hide_index=True, width="stretch", height=360)
