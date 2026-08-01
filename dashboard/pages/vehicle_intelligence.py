"""Vehicle Intelligence page powered by Phase 5A analytics output."""

from __future__ import annotations

import sqlite3

import streamlit as st
from components.intelligence import (
    format_eur,
    format_percentage,
    quantitative_table_rows,
    render_intelligence_unavailable,
    render_quantitative_score_cards,
    render_report_notice,
    render_score_card,
)
from components.page_header import render_page_header
from components.peer_benchmarking import (
    peer_overview_rows,
    render_compact_peer_summary,
)
from services.intelligence import DailyMarketIntelligence, vehicle_key
from services.peer_benchmarking import load_peer_benchmarks


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
) -> None:
    """Render dynamic vehicle filtering, metrics, and opportunity scoring."""

    render_page_header(
        title="Vehicle Intelligence",
        subtitle=(
            "Review inventory, asking prices, price trends, and market opportunity "
            "by brand and vehicle."
        ),
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("The current report contains no vehicle records.")
        return

    brands = sorted({item.brand for item in report.vehicles})
    filter_columns = st.columns((1, 1, 2))
    selected_brand = filter_columns[0].selectbox("Brand", brands)
    models = sorted(
        item.model for item in report.vehicles if item.brand == selected_brand
    )
    selected_model = filter_columns[1].selectbox("Vehicle", models)
    selected = next(
        item
        for item in report.vehicles
        if item.brand == selected_brand and item.model == selected_model
    )

    metrics = selected.metrics
    with st.container(horizontal=True):
        st.metric("Active listings", f"{metrics.active_listing_count:,}", border=True)
        st.metric(
            "Average asking price", format_eur(metrics.average_price_eur), border=True
        )
        st.metric(
            "Minimum asking price", format_eur(metrics.minimum_price_eur), border=True
        )
        st.metric(
            "Maximum asking price", format_eur(metrics.maximum_price_eur), border=True
        )
        st.metric(
            "New listings (7 days)", f"{metrics.new_listings_count_7d:,}", border=True
        )

    with st.container(horizontal=True):
        st.metric(
            "7-day price change",
            format_percentage(metrics.price_change_7d_pct, signed=True),
            border=True,
        )
        st.metric(
            "30-day price change",
            format_percentage(metrics.price_change_30d_pct, signed=True),
            border=True,
        )
        st.metric(
            "7-day inventory change",
            f"{metrics.inventory_change_7d_count:+,}",
            delta=format_percentage(metrics.inventory_change_7d_pct, signed=True),
            border=True,
        )

    render_score_card(selected)
    selected_scores = report.quantitative_by_vehicle[
        vehicle_key(selected.brand, selected.model)
    ]
    render_quantitative_score_cards(selected_scores, show_explanation=True)

    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.subheader("Peer Benchmarking")
        st.info(
            "insufficient_data: comparable-vehicle controls are unavailable. "
            f"Reason: {exc}"
        )
    else:
        render_compact_peer_summary(peer_report, selected)
        st.dataframe(
            peer_overview_rows(peer_report),
            hide_index=True,
            width="stretch",
            height=430,
        )

    st.subheader("Vehicle quantitative ranking")
    ranked = sorted(
        report.vehicles,
        key=lambda item: (
            report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].market_momentum.score
            is not None,
            report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].market_momentum.score
            or -1,
        ),
        reverse=True,
    )
    rows_by_vehicle = {
        vehicle_key(str(row["Brand"]), str(row["Vehicle"])): row
        for row in quantitative_table_rows(report)
    }
    st.dataframe(
        [rows_by_vehicle[vehicle_key(item.brand, item.model)] for item in ranked],
        hide_index=True,
        width="stretch",
        height=520,
    )
