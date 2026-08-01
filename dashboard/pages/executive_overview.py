"""Executive Overview page."""

from __future__ import annotations

import html
import sqlite3

import streamlit as st
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
        subtitle="德国汽车市场 KPI、趋势、机会、风险与每日情报流水线总览。",
    )

    if report is None:
        render_intelligence_unavailable(error_message)
    else:
        render_report_notice(report)
        _render_market_kpis(report)
        _render_quantitative_overview(report)
        _render_opportunity_and_trends(report)

    _render_pipeline_status(pipeline, pipeline_error)
    _render_ai_summary(ai_report, ai_error, report)

    if report is not None:
        ranked = sorted(
            report.vehicles,
            key=lambda item: item.opportunity_score.score,
            reverse=True,
        )
        st.subheader("重点车型")
        if ranked:
            st.dataframe(
                vehicle_table_rows(ranked[:5]),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("当前 Analytics 报告没有可展示的车型记录。")


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
            "活跃挂牌库存",
            f"{report.active_inventory_count:,}",
            border=True,
        )
        st.metric(
            f"当日新增挂牌 · {report.report_date:%m-%d}",
            "数据不足" if daily_new_count is None else f"{daily_new_count:,}",
            border=True,
        )
        st.metric(
            "加权平均挂牌价",
            format_eur(report.weighted_average_price_eur),
            border=True,
        )
        st.metric(
            "7日加权价格变化",
            format_percentage(_weighted_price_change(report), signed=True),
            border=True,
        )
        st.metric(
            "7日库存变化",
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
            "Price Pressure 总览",
            "数据不足" if price_score is None else f"{price_score:.2f}",
            border=True,
            help=f"可计算车型 {price_coverage}/{len(report.vehicles)}；车型等权平均。",
        )
        st.metric(
            "Inventory Pressure 总览",
            "数据不足" if inventory_score is None else f"{inventory_score:.2f}",
            border=True,
            help=(
                f"可计算车型 {inventory_coverage}/{len(report.vehicles)}；"
                "车型等权平均。"
            ),
        )
        st.metric(
            "Market Momentum",
            "数据不足" if momentum_score is None else f"{momentum_score:.2f}",
            border=True,
            help=(
                f"可计算车型 {momentum_coverage}/{len(report.vehicles)}；"
                "买方机会视角，不代表销量动能。"
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
            st.info("当前没有达到 70 分高压力阈值的可计算车型。")
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
            st.info("当前没有达到 60 分 Positive 阈值的可计算车型。")


def _render_opportunity_and_trends(report: DailyMarketIntelligence) -> None:
    ranked = sorted(
        report.vehicles,
        key=lambda item: item.opportunity_score.score,
        reverse=True,
    )
    st.subheader("Market Opportunity")
    if not ranked:
        st.info("当前没有可计算的车型机会信号。")
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
                        活跃挂牌 {vehicle.metrics.active_listing_count:,} ·
                        7日新增 {vehicle.metrics.new_listings_count_7d:,}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    trend_rows = [
        {
            "品牌": item.brand,
            "车型": item.model,
            "7日价格变化(%)": item.metrics.price_change_7d_pct,
            "30日价格变化(%)": item.metrics.price_change_30d_pct,
            "7日库存变化": item.metrics.inventory_change_7d_count,
        }
        for item in sorted(
            report.vehicles,
            key=lambda item: abs(item.metrics.price_change_7d_pct or 0),
            reverse=True,
        )[:8]
    ]
    st.subheader("市场趋势")
    if not any(row["7日价格变化(%)"] is not None for row in trend_rows):
        st.info("当前报告尚无完整的 7 日价格历史基线；库存变化仍可在车型页面查看。")
    st.dataframe(trend_rows, hide_index=True, width="stretch")


def _render_pipeline_status(
    pipeline: PipelineStatus | None,
    error_message: str | None,
) -> None:
    st.subheader("Pipeline Status")
    if pipeline is None:
        st.warning(error_message or "Pipeline 状态工件当前不可用。")
        return
    rows = [
        {
            "阶段": _STAGE_LABELS[stage],
            "状态": pipeline.stages[stage],
            "完成时间(UTC)": _stage_timestamp(pipeline, stage),
            "错误信息": pipeline.errors.get(stage),
        }
        for stage in PIPELINE_STAGES
    ]
    with st.container(horizontal=True):
        st.metric("Pipeline", pipeline.overall_status, border=True)
        st.metric("Run ID", pipeline.run_id or "未提供", border=True)
        st.metric(
            "最新状态时间",
            (
                pipeline.latest_timestamp.strftime("%Y-%m-%d %H:%M UTC")
                if pipeline.latest_timestamp is not None
                else "未提供"
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
        st.warning(error_message or "每日 AI Market Report 当前不可用。")
        return
    if analytics is not None and report.analytics_date != analytics.report_date:
        st.warning(
            "AI Report 与 Analytics 日期不一致；以下内容按 AI 报告自身日期展示。"
        )
    st.caption(
        f"Analytics date: {report.analytics_date.isoformat()} · "
        f"generation mode: {report.generation_mode}"
    )
    with st.container(border=True):
        st.markdown(report.market_overview_markdown)
    opportunity_column, risk_column = st.columns(2)
    with opportunity_column, st.container(border=True):
        st.subheader("市场机会")
        st.markdown(report.market_opportunity_markdown)
    with risk_column, st.container(border=True):
        st.subheader("Risk Alert")
        st.markdown(report.risk_markdown)
    with st.expander("查看完整 AI Market Report"):
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
