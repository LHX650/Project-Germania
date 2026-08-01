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
        subtitle="比较品牌库存规模、平均挂牌价、新能源结构与车型覆盖。",
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.brands:
        st.info("当前报告没有可展示的品牌记录。")
        return

    ranked = sorted(
        report.brands,
        key=lambda item: (
            item.metrics.active_inventory_rank,
            item.brand.casefold(),
        ),
    )
    selected_brand = st.selectbox("聚焦品牌", [item.brand for item in ranked])
    selected = next(item for item in ranked if item.brand == selected_brand)
    metrics = selected.metrics
    with st.container(horizontal=True):
        st.metric("库存排名", f"#{metrics.active_inventory_rank}", border=True)
        st.metric("活跃库存", f"{metrics.active_inventory_count:,}", border=True)
        st.metric(
            "平均挂牌价",
            format_eur(metrics.average_vehicle_price_eur),
            border=True,
        )
        st.metric(
            "BEV + PHEV 占比",
            format_percentage(metrics.bev_phev_share_pct),
            border=True,
        )
        st.metric(
            "车型覆盖率",
            format_percentage(metrics.model_coverage_pct),
            border=True,
        )

    _render_brand_peer_view(report, selected_brand)

    chart_rows = [
        {
            "品牌": item.brand,
            "活跃库存": item.metrics.active_inventory_count,
        }
        for item in ranked
    ]
    st.subheader("品牌库存竞争格局")
    with st.container(border=True):
        st.bar_chart(
            chart_rows,
            x="品牌",
            y="活跃库存",
            color="#376f93",
            height=360,
        )

    st.subheader("品牌指标明细")
    rows = [
        {
            "排名": item.metrics.active_inventory_rank,
            "品牌": item.brand,
            "活跃库存": item.metrics.active_inventory_count,
            "平均挂牌价(EUR)": item.metrics.average_vehicle_price_eur,
            "BEV占比(%)": item.metrics.bev_share_pct,
            "PHEV占比(%)": item.metrics.phev_share_pct,
            "BEV+PHEV占比(%)": item.metrics.bev_phev_share_pct,
            "车型覆盖": (
                f"{item.metrics.model_coverage_count}/"
                f"{item.metrics.catalog_model_count}"
            ),
            "覆盖率(%)": item.metrics.model_coverage_pct,
        }
        for item in ranked
    ]
    st.dataframe(rows, hide_index=True, width="stretch", height=470)


def _render_brand_peer_view(
    report: DailyMarketIntelligence,
    selected_brand: str,
) -> None:
    st.subheader("品牌车型同类基准")
    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.info(f"insufficient_data：可比车型控制变量当前不可用。原因：{exc}")
        return
    keys = {
        vehicle_key(item.brand, item.model)
        for item in report.vehicles
        if item.brand == selected_brand
    }
    rows = peer_overview_rows(peer_report, vehicle_keys=keys)
    if not rows:
        st.info("insufficient_data：该品牌当前没有 Analytics 车型记录。")
        return
    comparable = [
        row
        for row in rows
        if row["状态"] == "ok" and row["Opportunity Score Gap"] is not None
    ]
    if comparable:
        with st.container(border=True):
            st.bar_chart(
                comparable,
                x="车型",
                y="Opportunity Score Gap",
                color="#376f93",
                height=300,
            )
        st.caption(
            "每个车型均与自己的动态 Peer Group 比较，不直接把不同级别车型混为同一基准。"
        )
    st.dataframe(rows, hide_index=True, width="stretch", height=360)
