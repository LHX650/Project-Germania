"""Executive Overview page."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st
from components.ai_intelligence import (
    render_daily_market_brief,
    render_free_analyst,
)
from components.executive_brief import render_executive_intelligence_brief
from components.intelligence import (
    average_quantitative_score,
    format_eur,
    format_index_score,
    format_percentage,
    render_intelligence_unavailable,
    render_report_notice,
    vehicle_table_rows,
)
from components.page_header import render_page_header
from services.ai_report import AIMarketReport
from services.database import count_new_listings_on
from services.intelligence import DailyMarketIntelligence
from services.pipeline_status import PIPELINE_STAGES, PipelineStatus

_STAGE_LABELS = {
    "collection": "Collection",
    "analytics": "Analytics",
    "ai": "AI Report",
    "external_intelligence": "External Intelligence",
    "content_feed": "Content Feed",
    "executive_brief": "Executive Brief",
    "strategic": "Strategic Report",
}


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
    *,
    ai_report: AIMarketReport | None = None,
    ai_error: str | None = None,
    pipeline: PipelineStatus | None = None,
    pipeline_error: str | None = None,
) -> None:
    """Render a management summary from Analytics, AI, Pipeline, and SQLite."""

    render_page_header(
        title="Executive Overview",
        subtitle=(
            "German automotive market KPIs, trends, opportunities, risks, and "
            "daily intelligence pipeline status."
        ),
    )

    if report is None:
        render_intelligence_unavailable(error_message)
    else:
        render_report_notice(report)
        _render_market_kpis(report)
        _render_quantitative_overview(report)
        _render_opportunity_and_trends(report)
        render_daily_market_brief(report)

    render_executive_intelligence_brief(report)

    _render_pipeline_status(pipeline, pipeline_error)
    _render_ai_summary(ai_report, ai_error, report)
    render_free_analyst(report)

    if report is not None:
        ranked = sorted(
            report.vehicles,
            key=lambda item: item.opportunity_score.score,
            reverse=True,
        )
        st.subheader("Priority vehicles")
        if ranked:
            st.dataframe(
                vehicle_table_rows(ranked[:5]),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("The current Analytics report contains no vehicle records.")


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
            "Active listing inventory",
            f"{report.active_inventory_count:,}",
            border=True,
        )
        st.metric(
            f"New listings today · {report.report_date:%m-%d}",
            "Insufficient data" if daily_new_count is None else f"{daily_new_count:,}",
            border=True,
        )
        st.metric(
            "Weighted average asking price",
            format_eur(report.weighted_average_price_eur),
            border=True,
        )
        st.metric(
            "Weighted 7-day price change",
            format_percentage(_weighted_price_change(report), signed=True),
            border=True,
        )
        st.metric(
            "7-day inventory change",
            f"{inventory_change:+,}",
            border=True,
        )


def _render_quantitative_overview(report: DailyMarketIntelligence) -> None:
    st.subheader("Quantitative Market Signals")
    price_score, price_coverage = average_quantitative_score(report, "price_pressure")
    inventory_score, inventory_coverage = average_quantitative_score(
        report, "inventory_pressure"
    )
    momentum_score, momentum_coverage = average_quantitative_score(
        report, "market_momentum"
    )
    with st.container(horizontal=True):
        st.metric(
            "Price Pressure Index",
            "Insufficient data" if price_score is None else f"{price_score:.2f}",
            border=True,
            help=(
                f"Available for {price_coverage}/{len(report.vehicles)} vehicles; "
                "unweighted vehicle average."
            ),
        )
        st.metric(
            "Inventory Pressure Index",
            (
                "Insufficient data"
                if inventory_score is None
                else f"{inventory_score:.2f}"
            ),
            border=True,
            help=(
                f"Available for {inventory_coverage}/{len(report.vehicles)} vehicles; "
                "unweighted vehicle average."
            ),
        )
        st.metric(
            "Market Momentum",
            "Insufficient data" if momentum_score is None else f"{momentum_score:.2f}",
            border=True,
            help=(
                f"Available for {momentum_coverage}/{len(report.vehicles)} vehicles; "
                "a buyer-opportunity signal, not sales momentum."
            ),
        )
    _render_quantitative_alerts(report)


def _render_quantitative_alerts(report: DailyMarketIntelligence) -> None:
    price_risks = sorted(
        (
            score
            for score in report.quantitative_scores
            if score.price_pressure.score is not None
            and score.price_pressure.score >= 70
        ),
        key=lambda item: item.price_pressure.score or 0,
        reverse=True,
    )
    inventory_risks = sorted(
        (
            score
            for score in report.quantitative_scores
            if score.inventory_pressure.score is not None
            and score.inventory_pressure.score >= 70
        ),
        key=lambda item: item.inventory_pressure.score or 0,
        reverse=True,
    )
    opportunities = sorted(
        (
            score
            for score in report.quantitative_scores
            if score.market_momentum.score is not None
            and score.market_momentum.score >= 60
        ),
        key=lambda item: item.market_momentum.score or 0,
        reverse=True,
    )
    risk_column, opportunity_column = st.columns(2)
    with risk_column, st.container(border=True):
        st.markdown("**Risk alerts**")
        if price_risks or inventory_risks:
            for item in price_risks[:2]:
                st.warning(
                    f"{item.vehicle_key} · Price Pressure "
                    f"{format_index_score(item.price_pressure)}",
                    icon=":material/trending_down:",
                )
            for item in inventory_risks[:2]:
                st.warning(
                    f"{item.vehicle_key} · Inventory Pressure "
                    f"{format_index_score(item.inventory_pressure)}",
                    icon=":material/inventory_2:",
                )
        else:
            st.info(
                "No calculable vehicle currently exceeds the 70-point "
                "pressure threshold."
            )
    with opportunity_column, st.container(border=True):
        st.markdown("**Opportunity alerts**")
        if opportunities:
            for item in opportunities[:3]:
                st.success(
                    f"{item.vehicle_key} · {item.market_momentum.label} · "
                    f"{format_index_score(item.market_momentum)}",
                    icon=":material/insights:",
                )
        else:
            st.info(
                "No calculable vehicle currently reaches the 60-point "
                "Positive threshold."
            )


def _render_opportunity_and_trends(report: DailyMarketIntelligence) -> None:
    ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    st.subheader("Market Opportunity")
    if not ranked:
        st.info("No calculable vehicle opportunity signal is currently available.")
        return
    signal_columns = st.columns(3)
    for column, vehicle in zip(signal_columns, ranked[:3], strict=False):
        with column:
            st.markdown(
                f"""
                <div class="insight-card">
                    <div class="insight-card-label">OPPORTUNITY SIGNAL</div>
                    <div class="insight-card-title">
                        {html.escape(vehicle.brand)} · {html.escape(vehicle.model)}
                    </div>
                    <div class="insight-card-value">
                        {vehicle.opportunity_score.score:.2f}
                    </div>
                    <div class="insight-card-meta">
                        Active listings {vehicle.metrics.active_listing_count:,} ·
                        New listings (7 days) {vehicle.metrics.new_listings_count_7d:,}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    trend_rows = [
        {
            "Brand": item.brand,
            "Vehicle": item.model,
            "7-day price change (%)": item.metrics.price_change_7d_pct,
            "30-day price change (%)": item.metrics.price_change_30d_pct,
            "7-day inventory change": item.metrics.inventory_change_7d_count,
        }
        for item in sorted(
            report.vehicles,
            key=lambda item: abs(item.metrics.price_change_7d_pct or 0),
            reverse=True,
        )[:8]
    ]
    st.subheader("Market trends")
    if not any(row["7-day price change (%)"] is not None for row in trend_rows):
        st.info(
            "The report does not yet contain a complete 7-day price baseline. "
            "Inventory changes remain available on vehicle pages."
        )
    st.dataframe(trend_rows, hide_index=True, width="stretch")


def _render_pipeline_status(
    pipeline: PipelineStatus | None,
    error_message: str | None,
) -> None:
    st.subheader("Pipeline Status")
    if pipeline is None:
        st.warning(error_message or "The pipeline status artifact is unavailable.")
        return
    rows = [
        {
            "Stage": _STAGE_LABELS[stage],
            "Status": pipeline.stages[stage],
            "Completed at (UTC)": _stage_timestamp(pipeline, stage),
            "Error": pipeline.errors.get(stage),
        }
        for stage in PIPELINE_STAGES
    ]
    with st.container(horizontal=True):
        st.metric("Pipeline", pipeline.overall_status, border=True)
        st.metric("Run ID", pipeline.run_id or "Not provided", border=True)
        st.metric(
            "Latest status timestamp",
            (
                pipeline.latest_timestamp.strftime("%Y-%m-%d %H:%M UTC")
                if pipeline.latest_timestamp is not None
                else "Not provided"
            ),
            border=True,
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_ai_summary(
    report: AIMarketReport | None,
    error_message: str | None,
    analytics: DailyMarketIntelligence | None,
) -> None:
    st.subheader("AI Summary")
    if report is None:
        st.warning(error_message or "The daily AI Market Report is unavailable.")
        return
    if analytics is not None and report.analytics_date != analytics.report_date:
        st.warning(
            "The AI Report and Analytics dates do not match. Content below uses "
            "the date declared by the AI Report."
        )
    st.caption(
        f"Analytics date: {report.analytics_date.isoformat()} · "
        f"generation mode: {report.generation_mode}"
    )
    with st.container(border=True):
        st.markdown(report.market_overview_markdown)
    opportunity_column, risk_column = st.columns(2)
    with opportunity_column, st.container(border=True):
        st.subheader("Market Opportunity")
        st.markdown(report.market_opportunity_markdown)
    with risk_column, st.container(border=True):
        st.subheader("Risk Alert")
        st.markdown(report.risk_markdown)
    with st.expander("View full AI Market Report"):
        st.markdown(report.raw_markdown)


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


def _stage_timestamp(pipeline: PipelineStatus, stage: str) -> str | None:
    timestamp = pipeline.timestamps.get(f"{stage}_completed_at")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp is not None else None
