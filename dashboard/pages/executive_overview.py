"""Decision-focused Executive Overview page."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st
from components.ai_intelligence import render_free_analyst
from components.executive_brief import render_executive_intelligence_brief
from components.intelligence import (
    average_quantitative_score,
    format_eur,
    format_percentage,
    render_intelligence_unavailable,
)
from components.page_header import render_page_header
from services.ai_report import AIMarketReport
from services.database import count_new_listings_on
from services.intelligence import DailyMarketIntelligence, vehicle_key
from services.pipeline_status import PipelineStatus


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
    *,
    ai_report: AIMarketReport | None = None,
    ai_error: str | None = None,
    pipeline: PipelineStatus | None = None,
    pipeline_error: str | None = None,
) -> None:
    """Render a concise management view with progressive disclosure."""

    render_page_header(
        title="Executive Overview",
        subtitle=(
            "Prioritize the latest German automotive market changes, risks, "
            "and opportunities from one decision-focused view."
        ),
    )
    _render_compact_status_bar(report, pipeline)

    if report is None:
        render_intelligence_unavailable(error_message)
        render_executive_intelligence_brief(None)
    else:
        _render_market_kpis(report)
        _render_key_developments(report)
        render_executive_intelligence_brief(report)
        _render_market_pulse(report)
        _render_vehicles_to_watch(report)

    _render_secondary_resources(
        report,
        ai_report=ai_report,
        ai_error=ai_error,
        pipeline=pipeline,
        pipeline_error=pipeline_error,
    )


def _render_compact_status_bar(
    report: DailyMarketIntelligence | None,
    pipeline: PipelineStatus | None,
) -> None:
    report_date = (
        report.report_date.isoformat() if report is not None else "Unavailable"
    )
    vehicle_coverage = (
        f"{len(report.vehicles)} vehicles · {len(report.brands)} brands"
        if report is not None
        else "Unavailable"
    )
    system_health = (
        pipeline.overall_status.replace("_", " ").title()
        if pipeline is not None
        else "Unavailable"
    )
    updated_at = (
        pipeline.latest_timestamp.strftime("%Y-%m-%d %H:%M UTC")
        if pipeline is not None and pipeline.latest_timestamp is not None
        else "Not provided"
    )
    st.markdown(
        f"""
        <div class="executive-status-bar">
            <span class="status-pill"><strong>Data date</strong>
                {html.escape(report_date)}</span>
            <span class="status-pill"><strong>Coverage</strong>
                {html.escape(vehicle_coverage)}</span>
            <span class="status-pill"><strong>System health</strong>
                {html.escape(system_health)}</span>
            <span class="status-pill"><strong>Last update</strong>
                {html.escape(updated_at)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_market_kpis(report: DailyMarketIntelligence) -> None:
    try:
        daily_new_count: int | None = count_new_listings_on(report.report_date)
    except (FileNotFoundError, sqlite3.Error):
        daily_new_count = None
    inventory_change = sum(
        item.metrics.inventory_change_7d_count for item in report.vehicles
    )

    with st.container(horizontal=True):
        st.metric(
            "Active listings",
            f"{report.active_inventory_count:,}",
            border=True,
        )
        st.metric(
            "New today",
            "Insufficient data" if daily_new_count is None else f"{daily_new_count:,}",
            border=True,
        )
        st.metric(
            "Avg asking price",
            format_eur(report.weighted_average_price_eur),
            border=True,
        )
        st.metric(
            "7D price change",
            format_percentage(_weighted_price_change(report), signed=True),
            border=True,
        )
        st.metric(
            "7D inventory change",
            f"{inventory_change:+,}",
            border=True,
        )


def _render_key_developments(report: DailyMarketIntelligence) -> None:
    st.subheader("Today's key developments")
    price_movers = tuple(
        item for item in report.vehicles if item.metrics.price_change_7d_pct is not None
    )
    inventory_movers = tuple(
        item
        for item in report.vehicles
        if item.metrics.inventory_change_7d_pct is not None
    )
    opportunity_ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    developments: list[tuple[str, str]] = []
    if price_movers:
        vehicle = max(
            price_movers,
            key=lambda item: abs(item.metrics.price_change_7d_pct or 0),
        )
        price_change = format_percentage(
            vehicle.metrics.price_change_7d_pct,
            signed=True,
        )
        developments.append(
            (
                "Largest price movement",
                f"{vehicle.brand} {vehicle.model}: {price_change} over 7 days.",
            )
        )
    if inventory_movers:
        vehicle = max(
            inventory_movers,
            key=lambda item: abs(item.metrics.inventory_change_7d_pct or 0),
        )
        inventory_change = format_percentage(
            vehicle.metrics.inventory_change_7d_pct,
            signed=True,
        )
        developments.append(
            (
                "Largest inventory movement",
                f"{vehicle.brand} {vehicle.model}: {inventory_change} over 7 days.",
            )
        )
    if opportunity_ranked:
        vehicle = opportunity_ranked[0]
        developments.append(
            (
                "Leading opportunity signal",
                f"{vehicle.brand} {vehicle.model}: "
                f"{vehicle.opportunity_score.score:.2f}/100.",
            )
        )

    if not developments:
        st.info("No sufficiently supported daily developments are available.")
        return
    columns = st.columns(len(developments))
    for column, (title, description) in zip(columns, developments, strict=True):
        with column, st.container(border=True, height="stretch"):
            st.markdown(f"**{title}**")
            st.write(description)
    st.caption(
        "Movements use asking-price and active-listing observations; they do not "
        "represent transaction prices or vehicle sales."
    )


def _render_market_pulse(report: DailyMarketIntelligence) -> None:
    st.subheader("Market pulse")
    price_score, price_coverage = average_quantitative_score(report, "price_pressure")
    inventory_score, inventory_coverage = average_quantitative_score(
        report, "inventory_pressure"
    )
    momentum_score, momentum_coverage = average_quantitative_score(
        report, "market_momentum"
    )
    score_rows = [
        {"Signal": "Price pressure", "Score": price_score},
        {"Signal": "Inventory pressure", "Score": inventory_score},
        {"Signal": "Market momentum", "Score": momentum_score},
    ]
    score_rows = [row for row in score_rows if row["Score"] is not None]
    relationship_rows = [
        {
            "Vehicle": f"{item.brand} {item.model}",
            "7-day inventory change (%)": item.metrics.inventory_change_7d_pct,
            "7-day asking-price change (%)": item.metrics.price_change_7d_pct,
            "Active listings": item.metrics.active_listing_count,
        }
        for item in report.vehicles
        if item.metrics.inventory_change_7d_pct is not None
        and item.metrics.price_change_7d_pct is not None
    ]
    first, second = st.columns(2)
    with first, st.container(border=True, height="stretch"):
        st.markdown("**Current market signals**")
        if score_rows:
            st.bar_chart(score_rows, x="Signal", y="Score", height=280)
        else:
            st.info("Insufficient data for the quantitative market signals.")
        st.caption(
            f"Coverage: price {price_coverage}/{len(report.vehicles)}, "
            f"inventory {inventory_coverage}/{len(report.vehicles)}, "
            f"momentum {momentum_coverage}/{len(report.vehicles)}."
        )
    with second, st.container(border=True, height="stretch"):
        st.markdown("**Price and inventory movement**")
        if relationship_rows:
            st.scatter_chart(
                relationship_rows,
                x="7-day inventory change (%)",
                y="7-day asking-price change (%)",
                size="Active listings",
                color="#376f93",
                height=280,
            )
        else:
            st.info("Insufficient data for a joint 7-day movement view.")


def _render_vehicles_to_watch(report: DailyMarketIntelligence) -> None:
    st.subheader("Vehicles to watch")
    ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )[:5]
    if not ranked:
        st.info("No vehicle watchlist can be calculated from the current report.")
        return
    rows = []
    for item in ranked:
        scores = report.quantitative_by_vehicle[vehicle_key(item.brand, item.model)]
        rows.append(
            {
                "Vehicle": f"{item.brand} {item.model}",
                "Opportunity Score": item.opportunity_score.score,
                "Price Pressure": scores.price_pressure.score,
                "Inventory Pressure": scores.inventory_pressure.score,
                "Market Momentum": scores.market_momentum.score,
                "Active listings": item.metrics.active_listing_count,
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_secondary_resources(
    report: DailyMarketIntelligence | None,
    *,
    ai_report: AIMarketReport | None,
    ai_error: str | None,
    pipeline: PipelineStatus | None,
    pipeline_error: str | None,
) -> None:
    with st.expander("Full daily market report"):
        if ai_report is None:
            st.info(ai_error or "The daily market report is unavailable.")
        else:
            if report is not None and ai_report.analytics_date != report.report_date:
                st.warning(
                    "The market report and Analytics dates do not match. The "
                    "content below uses the date declared by the report."
                )
            st.markdown(ai_report.raw_markdown)

    with st.expander("Explore with the market analyst"):
        render_free_analyst(report)

    with st.expander("Data notes and methodology"):
        if report is None:
            st.info("Analytics methodology is unavailable.")
        else:
            st.json(report.methodology)
        if pipeline is None:
            st.caption(pipeline_error or "System status details are unavailable.")
        else:
            st.caption(
                f"System status: {pipeline.overall_status.replace('_', ' ')} · "
                f"Latest status: "
                f"{pipeline.latest_timestamp or 'Not provided'}"
            )
        st.caption(
            "Asking prices are not transaction prices, and listing inventory is "
            "not vehicle sales. Detailed system health remains available on Data "
            "Quality."
        )


def _weighted_price_change(report: DailyMarketIntelligence) -> float | None:
    available = tuple(
        item
        for item in report.vehicles
        if item.metrics.price_change_7d_pct is not None
        and item.metrics.active_listing_count > 0
    )
    denominator = sum(item.metrics.active_listing_count for item in available)
    if denominator == 0:
        return None
    return (
        sum(
            item.metrics.price_change_7d_pct * item.metrics.active_listing_count
            for item in available
            if item.metrics.price_change_7d_pct is not None
        )
        / denominator
    )
