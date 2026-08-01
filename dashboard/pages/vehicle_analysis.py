"""Deep, read-only Vehicle Analysis page."""

from __future__ import annotations

import sqlite3
from collections import Counter
from decimal import Decimal

import streamlit as st
from components.intelligence import (
    format_eur,
    format_percentage,
    render_intelligence_unavailable,
    render_quantitative_score_cards,
    render_report_notice,
    render_score_card,
)
from components.page_header import render_page_header
from components.peer_benchmarking import render_peer_comparison
from services.content_feed import ContentFeedError, ContentRecord, load_content_feed
from services.database import VehicleAnalysisSnapshot, load_vehicle_analysis
from services.intelligence import (
    DailyMarketIntelligence,
    VehicleIntelligence,
    vehicle_key,
)
from services.peer_benchmarking import load_peer_benchmarks


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
) -> None:
    """Render one selected vehicle's Analytics and SQLite evidence."""

    render_page_header(
        title="Vehicle Analysis",
        subtitle=(
            "Vehicle listings, price and inventory history, distributions, "
            "opportunity scoring, and related external intelligence."
        ),
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("The current report contains no vehicles for detailed analysis.")
        return

    selected = _vehicle_selector(report)
    _render_current_metrics(selected)
    render_score_card(selected)
    render_quantitative_score_cards(
        report.quantitative_by_vehicle[vehicle_key(selected.brand, selected.model)],
        show_explanation=True,
    )

    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.subheader("Peer Comparison")
        st.info(
            "insufficient_data: comparable-vehicle controls are unavailable. "
            f"Reason: {exc}"
        )
    else:
        render_peer_comparison(
            peer_report,
            report,
            selected,
            chart_key="vehicle_analysis_peer_metric",
        )

    try:
        snapshot = load_vehicle_analysis(selected.brand, selected.model)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.warning(f"Vehicle-level database details are unavailable: {exc}")
        st.info(
            "Current Analytics metrics remain available; distribution and history "
            "sections do not have database validation."
        )
        snapshot = None

    _render_trends(snapshot)
    _render_distributions(snapshot)
    _render_related_content(selected)


def _vehicle_selector(report: DailyMarketIntelligence) -> VehicleIntelligence:
    brands = sorted({item.brand for item in report.vehicles})
    columns = st.columns((1, 1, 2))
    selected_brand = columns[0].selectbox(
        "Brand",
        brands,
        key="vehicle_analysis_brand",
    )
    models = sorted(
        item.model for item in report.vehicles if item.brand == selected_brand
    )
    selected_model = columns[1].selectbox(
        "Vehicle",
        models,
        key="vehicle_analysis_model",
    )
    return next(
        item
        for item in report.vehicles
        if item.brand == selected_brand and item.model == selected_model
    )


def _render_current_metrics(vehicle: VehicleIntelligence) -> None:
    metrics = vehicle.metrics
    with st.container(horizontal=True):
        st.metric("Current listings", f"{metrics.active_listing_count:,}", border=True)
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
            "7-day price change",
            format_percentage(metrics.price_change_7d_pct, signed=True),
            border=True,
        )
    st.caption(
        "Current metrics come from Phase 5A Analytics. Asking prices are not "
        "transaction prices, and listing counts do not represent sales."
    )


def _render_trends(snapshot: VehicleAnalysisSnapshot | None) -> None:
    st.subheader("Price Trend & Inventory Trend")
    if snapshot is None or not snapshot.trend:
        st.info("No verifiable vehicle history observations are available.")
        return
    price_rows = [
        {
            "Date": point.observed_date,
            "Average asking price (EUR)": (
                float(point.average_price_eur)
                if point.average_price_eur is not None
                else None
            ),
        }
        for point in snapshot.trend
        if point.average_price_eur is not None
    ]
    inventory_rows = [
        {
            "Date": point.observed_date,
            "Observed active inventory": point.observed_active_inventory,
        }
        for point in snapshot.trend
    ]
    price_column, inventory_column = st.columns(2)
    with price_column:
        st.markdown("**Price Trend**")
        if len(price_rows) >= 2:
            st.line_chart(price_rows, x="Date", y="Average asking price (EUR)")
        elif price_rows:
            st.info(
                "Price history contains only one observation date, which is "
                "insufficient to establish a trend."
            )
            st.dataframe(price_rows, hide_index=True, width="stretch")
        else:
            st.info("Historical observations contain no valid EUR asking prices.")
    with inventory_column:
        st.markdown("**Inventory Trend**")
        if len(inventory_rows) >= 2:
            st.line_chart(inventory_rows, x="Date", y="Observed active inventory")
        else:
            st.info(
                "Inventory history contains only one observation date, which is "
                "insufficient to establish a trend."
            )
            st.dataframe(inventory_rows, hide_index=True, width="stretch")
        st.caption(
            "The inventory trend represents active listing coverage observed on "
            "each collection date; it does not represent vehicle sales."
        )


def _render_distributions(snapshot: VehicleAnalysisSnapshot | None) -> None:
    st.subheader("Listing distributions")
    if snapshot is None:
        st.info("No database distribution data is available.")
        return
    columns = st.columns(3)
    with columns[0]:
        st.markdown("**Price distribution**")
        price_rows = _histogram_rows(snapshot.prices_eur, unit="€")
        if price_rows:
            st.bar_chart(price_rows, x="Range", y="Listing count")
        else:
            st.info("No valid EUR price distribution is available.")
    with columns[1]:
        st.markdown("**Mileage distribution**")
        mileage_rows = _histogram_rows(snapshot.mileages_km, unit="km")
        if mileage_rows:
            st.bar_chart(mileage_rows, x="Range", y="Listing count")
        else:
            st.info("No valid mileage distribution is available.")
    with columns[2]:
        st.markdown("**Registration distribution**")
        registration_rows = [
            {"Registration year": str(year), "Listing count": count}
            for year, count in sorted(Counter(snapshot.registration_years).items())
        ]
        if registration_rows:
            st.bar_chart(registration_rows, x="Registration year", y="Listing count")
        else:
            st.info("No valid first-registration-year distribution is available.")


def _render_related_content(vehicle: VehicleIntelligence) -> None:
    st.subheader("Related news and official reports")
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.info(f"The external content feed is unavailable: {exc}")
        return
    related = tuple(
        item
        for item in feed.items
        if item.content_type in {"news", "report"} and _is_related(item, vehicle)
    )
    if not related:
        st.info(
            "The current feed contains no news or official reports with a "
            "verified association to this vehicle."
        )
        return
    for item in related[:6]:
        with st.container(border=True):
            st.caption(
                f"{item.content_type.upper()} · {item.source_name} · "
                f"{item.published_at:%Y-%m-%d}"
            )
            st.markdown(f"**{item.title}**")
            st.write(item.summary)
            link_label = (
                "View official report / source"
                if item.content_type == "report"
                else "Read original article"
            )
            st.link_button(
                link_label,
                item.document_url or item.source_url,
            )


def _histogram_rows(
    values: tuple[Decimal, ...] | tuple[int, ...],
    *,
    unit: str,
    bucket_count: int = 8,
) -> list[dict[str, object]]:
    numeric = [float(value) for value in values]
    if not numeric:
        return []
    lower = min(numeric)
    upper = max(numeric)
    if lower == upper:
        return [{"Range": f"{lower:,.0f} {unit}", "Listing count": len(numeric)}]
    width = (upper - lower) / bucket_count
    counts = [0] * bucket_count
    for value in numeric:
        index = min(int((value - lower) / width), bucket_count - 1)
        counts[index] += 1
    return [
        {
            "Range": (
                f"{lower + index * width:,.0f}–"
                f"{lower + (index + 1) * width:,.0f} {unit}"
            ),
            "Listing count": count,
        }
        for index, count in enumerate(counts)
        if count
    ]


def _is_related(item: ContentRecord, vehicle: VehicleIntelligence) -> bool:
    brand = _normalize(vehicle.brand)
    full_name = _normalize(f"{vehicle.brand} {vehicle.model}")
    return full_name in {_normalize(value) for value in item.vehicles} or brand in {
        _normalize(value) for value in item.brands
    }


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
