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
        subtitle="车型挂牌、价格与库存历史、分布、机会评分及相关外部情报。",
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("当前报告没有可供深度分析的车型记录。")
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
        st.info(f"insufficient_data：可比车型控制变量当前不可用。原因：{exc}")
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
        st.warning(f"车型数据库明细当前不可用：{exc}")
        st.info("Analytics 当前指标仍可使用；分布与历史部分暂无数据库验证。")
        snapshot = None

    _render_trends(snapshot)
    _render_distributions(snapshot)
    _render_related_content(selected)


def _vehicle_selector(report: DailyMarketIntelligence) -> VehicleIntelligence:
    brands = sorted({item.brand for item in report.vehicles})
    columns = st.columns((1, 1, 2))
    selected_brand = columns[0].selectbox(
        "品牌",
        brands,
        key="vehicle_analysis_brand",
    )
    models = sorted(
        item.model for item in report.vehicles if item.brand == selected_brand
    )
    selected_model = columns[1].selectbox(
        "车型",
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
        st.metric("当前挂牌", f"{metrics.active_listing_count:,}", border=True)
        st.metric("平均挂牌价", format_eur(metrics.average_price_eur), border=True)
        st.metric("最低挂牌价", format_eur(metrics.minimum_price_eur), border=True)
        st.metric("最高挂牌价", format_eur(metrics.maximum_price_eur), border=True)
        st.metric(
            "7日价格变化",
            format_percentage(metrics.price_change_7d_pct, signed=True),
            border=True,
        )
    st.caption(
        "当前指标来自 Phase 5A Analytics；挂牌价不是成交价，挂牌数量不代表销量。"
    )


def _render_trends(snapshot: VehicleAnalysisSnapshot | None) -> None:
    st.subheader("Price Trend & Inventory Trend")
    if snapshot is None or not snapshot.trend:
        st.info("暂无可验证的车型历史观测数据。")
        return
    price_rows = [
        {
            "日期": point.observed_date,
            "平均挂牌价(EUR)": (
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
            "日期": point.observed_date,
            "观测活跃库存": point.observed_active_inventory,
        }
        for point in snapshot.trend
    ]
    price_column, inventory_column = st.columns(2)
    with price_column:
        st.markdown("**Price Trend**")
        if len(price_rows) >= 2:
            st.line_chart(price_rows, x="日期", y="平均挂牌价(EUR)")
        elif price_rows:
            st.info("价格历史仅有一个观测日期，暂不足以形成趋势。")
            st.dataframe(price_rows, hide_index=True, width="stretch")
        else:
            st.info("历史观测中没有有效 EUR 挂牌价。")
    with inventory_column:
        st.markdown("**Inventory Trend**")
        if len(inventory_rows) >= 2:
            st.line_chart(inventory_rows, x="日期", y="观测活跃库存")
        else:
            st.info("库存历史仅有一个观测日期，暂不足以形成趋势。")
            st.dataframe(inventory_rows, hide_index=True, width="stretch")
    st.caption("库存趋势表示各采集日期实际观测到的活跃挂牌覆盖，不代表真实销量。")


def _render_distributions(snapshot: VehicleAnalysisSnapshot | None) -> None:
    st.subheader("挂牌分布")
    if snapshot is None:
        st.info("暂无数据库分布数据。")
        return
    columns = st.columns(3)
    with columns[0]:
        st.markdown("**Price distribution**")
        price_rows = _histogram_rows(snapshot.prices_eur, unit="€")
        if price_rows:
            st.bar_chart(price_rows, x="区间", y="挂牌数")
        else:
            st.info("暂无有效 EUR 价格分布。")
    with columns[1]:
        st.markdown("**Mileage distribution**")
        mileage_rows = _histogram_rows(snapshot.mileages_km, unit="km")
        if mileage_rows:
            st.bar_chart(mileage_rows, x="区间", y="挂牌数")
        else:
            st.info("暂无有效里程分布。")
    with columns[2]:
        st.markdown("**Registration distribution**")
        registration_rows = [
            {"注册年份": str(year), "挂牌数": count}
            for year, count in sorted(Counter(snapshot.registration_years).items())
        ]
        if registration_rows:
            st.bar_chart(registration_rows, x="注册年份", y="挂牌数")
        else:
            st.info("暂无有效首次注册年份分布。")


def _render_related_content(vehicle: VehicleIntelligence) -> None:
    st.subheader("相关新闻与官方报告")
    try:
        feed = load_content_feed()
    except ContentFeedError as exc:
        st.info(f"外部内容 Feed 当前不可用：{exc}")
        return
    related = tuple(
        item
        for item in feed.items
        if item.content_type in {"news", "report"} and _is_related(item, vehicle)
    )
    if not related:
        st.info("当前 Feed 中没有可确认关联的新闻或官方报告。")
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
                "查看官方报告 / 原始来源"
                if item.content_type == "report"
                else "阅读原文"
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
        return [{"区间": f"{lower:,.0f} {unit}", "挂牌数": len(numeric)}]
    width = (upper - lower) / bucket_count
    counts = [0] * bucket_count
    for value in numeric:
        index = min(int((value - lower) / width), bucket_count - 1)
        counts[index] += 1
    return [
        {
            "区间": (
                f"{lower + index * width:,.0f}–"
                f"{lower + (index + 1) * width:,.0f} {unit}"
            ),
            "挂牌数": count,
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
