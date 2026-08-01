"""Price Intelligence page powered by Phase 5A analytics output."""

from __future__ import annotations

import sqlite3

import streamlit as st
from components.intelligence import (
    format_index_score,
    render_intelligence_unavailable,
    render_report_notice,
)
from components.page_header import render_page_header
from components.peer_benchmarking import peer_overview_rows
from services.intelligence import (
    DailyMarketIntelligence,
    VehicleIntelligence,
    vehicle_key,
)
from services.peer_benchmarking import load_peer_benchmarks

from germania.analytics.quantitative_intelligence import QUANTITATIVE_METHODOLOGY


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
) -> None:
    """Render asking-price positioning and available trend coverage."""

    render_page_header(
        title="Price Intelligence",
        subtitle=(
            "Compare vehicle asking-price ranges and 7-day and 30-day price "
            "trends dynamically."
        ),
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("The current report contains no price records.")
        return

    all_brands = sorted({item.brand for item in report.vehicles})
    selected_brands = st.multiselect(
        "Brand filter",
        all_brands,
        default=all_brands,
    )
    filtered = tuple(item for item in report.vehicles if item.brand in selected_brands)
    if not filtered:
        st.info("Select at least one brand.")
        return

    _render_peer_price_view(report, filtered)

    rows = [
        {
            "Brand": item.brand,
            "Vehicle": item.model,
            "Average asking price": item.metrics.average_price_eur,
            "Minimum asking price": item.metrics.minimum_price_eur,
            "Maximum asking price": item.metrics.maximum_price_eur,
            "7-day price change (%)": item.metrics.price_change_7d_pct,
            "30-day price change (%)": item.metrics.price_change_30d_pct,
            "Active listings": item.metrics.active_listing_count,
            "Price Pressure": report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].price_pressure.score,
        }
        for item in sorted(
            filtered,
            key=lambda item: item.metrics.average_price_eur or float("inf"),
        )
    ]
    st.subheader("Average asking price by vehicle")
    chart_rows = [
        {
            "Vehicle": f"{item.brand} · {item.model}",
            "Average asking price": item.metrics.average_price_eur,
        }
        for item in filtered
        if item.metrics.average_price_eur is not None
    ]
    if chart_rows:
        with st.container(border=True):
            st.bar_chart(
                chart_rows,
                x="Vehicle",
                y="Average asking price",
                color="#376f93",
                height=360,
            )
    else:
        st.info("The selected vehicles do not have valid EUR asking prices.")

    available_7d = sum(
        item.metrics.price_change_7d_pct is not None for item in filtered
    )
    available_30d = sum(
        item.metrics.price_change_30d_pct is not None for item in filtered
    )
    with st.container(horizontal=True):
        st.metric(
            "7-day trend coverage",
            f"{available_7d}/{len(filtered)}",
            border=True,
        )
        st.metric(
            "30-day trend coverage",
            f"{available_30d}/{len(filtered)}",
            border=True,
        )
    if available_30d < len(filtered):
        st.info(
            "Some vehicles do not yet have a complete 30-day baseline; related "
            "metrics remain empty under the missing-data rules."
        )

    _render_price_pressure(report, filtered)
    st.dataframe(rows, hide_index=True, width="stretch", height=520)
    with st.expander("View metric formulas and missing-data rules"):
        st.markdown("**Phase 5A Analytics**")
        st.json(report.methodology)
        st.markdown("**Phase 11 Quantitative Intelligence**")
        st.json(QUANTITATIVE_METHODOLOGY)


def _render_peer_price_view(
    report: DailyMarketIntelligence,
    vehicles: tuple[VehicleIntelligence, ...],
) -> None:
    st.subheader("Peer asking-price benchmark")
    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.info(
            "insufficient_data: comparable-vehicle controls are unavailable. "
            f"Reason: {exc}"
        )
        return
    keys = {vehicle_key(item.brand, item.model) for item in vehicles}
    rows = peer_overview_rows(peer_report, vehicle_keys=keys)
    comparable = [
        row
        for row in rows
        if row["Status"] == "ok" and row["Average asking price Gap"] is not None
    ]
    if comparable:
        with st.container(border=True):
            st.bar_chart(
                comparable,
                x="Vehicle",
                y="Average asking price Gap",
                color="#376f93",
                height=340,
            )
        st.caption(
            "Gap is the target vehicle's average asking-price difference versus "
            "its dynamic Peer Median; a negative value is below the peer median."
        )
    else:
        st.info(
            "insufficient_data: the selected vehicles have no valid peer "
            "asking-price benchmark."
        )
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "Average asking price Gap": st.column_config.NumberColumn(format="%+.2f%%"),
            "Price Pressure Gap": st.column_config.NumberColumn(format="%+.2f"),
            "Inventory Pressure Gap": st.column_config.NumberColumn(format="%+.2f"),
            "Market Momentum Gap": st.column_config.NumberColumn(format="%+.2f"),
        },
    )


def _render_price_pressure(
    report: DailyMarketIntelligence,
    vehicles: tuple[VehicleIntelligence, ...],
) -> None:
    scored = [
        (
            item,
            report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].price_pressure,
        )
        for item in vehicles
    ]
    ranked = sorted(
        ((item, index) for item, index in scored if index.score is not None),
        key=lambda pair: pair[1].score or 0,
        reverse=True,
    )
    st.subheader("Price Pressure Ranking")
    if ranked:
        ranking_rows = [
            {
                "Vehicle": f"{item.brand} · {item.model}",
                "Price Pressure": index.score,
                "7-day price change (%)": item.metrics.price_change_7d_pct,
                "7-day inventory change (%)": item.metrics.inventory_change_7d_pct,
                "Asking-price dispersion": index.components["price_dispersion"],
            }
            for item, index in ranked
        ]
        with st.container(border=True):
            st.bar_chart(
                ranking_rows,
                x="Vehicle",
                y="Price Pressure",
                color="#b25d4b",
                height=340,
            )
        high_pressure = [pair for pair in ranked if (pair[1].score or 0) >= 70]
        if high_pressure:
            st.warning(
                "High-pressure vehicles: "
                + "; ".join(
                    f"{item.brand} {item.model} " f"({format_index_score(index)})"
                    for item, index in high_pressure
                ),
                icon=":material/warning:",
            )
    else:
        st.info(
            "The selected vehicles lack a 7-day price baseline, so Price Pressure "
            "cannot be calculated."
        )

    linkage_rows = [
        {
            "Vehicle": f"{item.brand} · {item.model}",
            "7-day price change (%)": item.metrics.price_change_7d_pct,
            "7-day inventory change (%)": item.metrics.inventory_change_7d_pct,
            "Active listings": item.metrics.active_listing_count,
        }
        for item in vehicles
        if item.metrics.price_change_7d_pct is not None
        and item.metrics.inventory_change_7d_pct is not None
    ]
    st.subheader("Price and inventory change relationship")
    if linkage_rows:
        with st.container(border=True):
            st.scatter_chart(
                linkage_rows,
                x="7-day inventory change (%)",
                y="7-day price change (%)",
                size="Active listings",
                color="#376f93",
                height=360,
            )
        st.caption(
            "This chart shows asking-price and listing-inventory signals only; it "
            "does not represent sales or transaction prices."
        )
    else:
        st.info(
            "The selected vehicles do not have jointly verifiable price and "
            "inventory change baselines."
        )
