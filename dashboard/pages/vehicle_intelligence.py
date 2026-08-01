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
        subtitle="按品牌与车型审视库存、挂牌价、价格趋势和市场机会。",
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("当前报告没有可展示的车型记录。")
        return

    brands = sorted({item.brand for item in report.vehicles})
    filter_columns = st.columns((1, 1, 2))
    selected_brand = filter_columns[0].selectbox("品牌", brands)
    models = sorted(
        item.model for item in report.vehicles if item.brand == selected_brand
    )
    selected_model = filter_columns[1].selectbox("车型", models)
    selected = next(
        item
        for item in report.vehicles
        if item.brand == selected_brand and item.model == selected_model
    )

    metrics = selected.metrics
    with st.container(horizontal=True):
        st.metric("活跃挂牌", f"{metrics.active_listing_count:,}", border=True)
        st.metric("平均挂牌价", format_eur(metrics.average_price_eur), border=True)
        st.metric("最低挂牌价", format_eur(metrics.minimum_price_eur), border=True)
        st.metric("最高挂牌价", format_eur(metrics.maximum_price_eur), border=True)
        st.metric("7日新增", f"{metrics.new_listings_count_7d:,}", border=True)

    with st.container(horizontal=True):
        st.metric(
            "7日价格变化",
            format_percentage(metrics.price_change_7d_pct, signed=True),
            border=True,
        )
        st.metric(
            "30日价格变化",
            format_percentage(metrics.price_change_30d_pct, signed=True),
            border=True,
        )
        st.metric(
            "7日库存变化",
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
        st.subheader("同类车型比较")
        st.info(f"insufficient_data：可比车型控制变量当前不可用。原因：{exc}")
    else:
        render_compact_peer_summary(peer_report, selected)
        st.dataframe(
            peer_overview_rows(peer_report),
            hide_index=True,
            width="stretch",
            height=430,
        )

    st.subheader("车型量化排名")
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
        vehicle_key(str(row["品牌"]), str(row["车型"])): row
        for row in quantitative_table_rows(report)
    }
    st.dataframe(
        [rows_by_vehicle[vehicle_key(item.brand, item.model)] for item in ranked],
        hide_index=True,
        width="stretch",
        height=520,
    )
