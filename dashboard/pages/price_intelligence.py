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
        subtitle="动态比较车型挂牌价格区间与 7/30 日价格趋势。",
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("当前报告没有可展示的价格记录。")
        return

    all_brands = sorted({item.brand for item in report.vehicles})
    selected_brands = st.multiselect(
        "品牌筛选",
        all_brands,
        default=all_brands,
    )
    filtered = tuple(item for item in report.vehicles if item.brand in selected_brands)
    if not filtered:
        st.info("请选择至少一个品牌。")
        return

    _render_peer_price_view(report, filtered)

    rows = [
        {
            "品牌": item.brand,
            "车型": item.model,
            "平均挂牌价": item.metrics.average_price_eur,
            "最低挂牌价": item.metrics.minimum_price_eur,
            "最高挂牌价": item.metrics.maximum_price_eur,
            "7日价格变化(%)": item.metrics.price_change_7d_pct,
            "30日价格变化(%)": item.metrics.price_change_30d_pct,
            "活跃挂牌": item.metrics.active_listing_count,
            "Price Pressure": report.quantitative_by_vehicle[
                vehicle_key(item.brand, item.model)
            ].price_pressure.score,
        }
        for item in sorted(
            filtered,
            key=lambda item: item.metrics.average_price_eur or float("inf"),
        )
    ]
    st.subheader("车型平均挂牌价")
    chart_rows = [
        {
            "车型": f"{item.brand} · {item.model}",
            "平均挂牌价": item.metrics.average_price_eur,
        }
        for item in filtered
        if item.metrics.average_price_eur is not None
    ]
    if chart_rows:
        with st.container(border=True):
            st.bar_chart(
                chart_rows,
                x="车型",
                y="平均挂牌价",
                color="#376f93",
                height=360,
            )
    else:
        st.info("所选车型缺少有效 EUR 挂牌价。")

    available_7d = sum(
        item.metrics.price_change_7d_pct is not None for item in filtered
    )
    available_30d = sum(
        item.metrics.price_change_30d_pct is not None for item in filtered
    )
    with st.container(horizontal=True):
        st.metric(
            "7日趋势覆盖",
            f"{available_7d}/{len(filtered)}",
            border=True,
        )
        st.metric(
            "30日趋势覆盖",
            f"{available_30d}/{len(filtered)}",
            border=True,
        )
    if available_30d < len(filtered):
        st.info("部分车型尚无完整 30 日历史基线，相关指标按规则显示为空。")

    _render_price_pressure(report, filtered)
    st.dataframe(rows, hide_index=True, width="stretch", height=520)
    with st.expander("查看指标公式与缺失数据规则"):
        st.markdown("**Phase 5A Analytics**")
        st.json(report.methodology)
        st.markdown("**Phase 11 Quantitative Intelligence**")
        st.json(QUANTITATIVE_METHODOLOGY)


def _render_peer_price_view(
    report: DailyMarketIntelligence,
    vehicles: tuple[VehicleIntelligence, ...],
) -> None:
    st.subheader("同类车型价格基准")
    try:
        peer_report = load_peer_benchmarks(report)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.info(f"insufficient_data：可比车型控制变量当前不可用。原因：{exc}")
        return
    keys = {vehicle_key(item.brand, item.model) for item in vehicles}
    rows = peer_overview_rows(peer_report, vehicle_keys=keys)
    comparable = [
        row for row in rows if row["状态"] == "ok" and row["平均挂牌价 Gap"] is not None
    ]
    if comparable:
        with st.container(border=True):
            st.bar_chart(
                comparable,
                x="车型",
                y="平均挂牌价 Gap",
                color="#376f93",
                height=340,
            )
        st.caption(
            "Gap 为目标车型相对其动态 Peer Median 的挂牌均价差；"
            "负值表示低于同类中位数。"
        )
    else:
        st.info("insufficient_data：当前筛选车型没有有效的同类挂牌价格基准。")
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "平均挂牌价 Gap": st.column_config.NumberColumn(format="%+.2f%%"),
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
                "车型": f"{item.brand} · {item.model}",
                "Price Pressure": index.score,
                "7日价格变化(%)": item.metrics.price_change_7d_pct,
                "7日库存变化(%)": item.metrics.inventory_change_7d_pct,
                "挂牌价离散度": index.components["price_dispersion"],
            }
            for item, index in ranked
        ]
        with st.container(border=True):
            st.bar_chart(
                ranking_rows,
                x="车型",
                y="Price Pressure",
                color="#b25d4b",
                height=340,
            )
        high_pressure = [pair for pair in ranked if (pair[1].score or 0) >= 70]
        if high_pressure:
            st.warning(
                "高压力车型："
                + "；".join(
                    f"{item.brand} {item.model} " f"({format_index_score(index)})"
                    for item, index in high_pressure
                ),
                icon=":material/warning:",
            )
    else:
        st.info("所选车型缺少 7 日价格基线，Price Pressure 暂不可计算。")

    linkage_rows = [
        {
            "车型": f"{item.brand} · {item.model}",
            "7日价格变化(%)": item.metrics.price_change_7d_pct,
            "7日库存变化(%)": item.metrics.inventory_change_7d_pct,
            "活跃挂牌": item.metrics.active_listing_count,
        }
        for item in vehicles
        if item.metrics.price_change_7d_pct is not None
        and item.metrics.inventory_change_7d_pct is not None
    ]
    st.subheader("价格变化与库存变化联动")
    if linkage_rows:
        with st.container(border=True):
            st.scatter_chart(
                linkage_rows,
                x="7日库存变化(%)",
                y="7日价格变化(%)",
                size="活跃挂牌",
                color="#376f93",
                height=360,
            )
        st.caption("联动图仅表示挂牌价格与库存信号，不表示销量或成交价格。")
    else:
        st.info("当前筛选车型缺少可同时验证的价格和库存变化基线。")
