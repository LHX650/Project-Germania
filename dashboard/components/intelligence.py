"""Reusable presentation helpers for intelligence report pages."""

from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st
from services.intelligence import (
    DailyMarketIntelligence,
    VehicleIntelligence,
    vehicle_key,
)

from germania.analytics.quantitative_intelligence import (
    QUANTITATIVE_METHODOLOGY,
    QuantitativeIndex,
    VehicleQuantitativeScores,
)

_QUANTITATIVE_COMPONENT_LABELS = {
    "price_decline_7d": "7日降价压力",
    "price_decline_30d": "30日降价压力",
    "inventory_growth": "库存增长压力",
    "price_dispersion": "挂牌价离散度",
    "inventory_level": "相对库存水平",
    "new_listing_intensity": "新增挂牌强度",
    "low_market_activity": "低市场活跃度",
    "new_listing_activity": "新增挂牌活动",
    "price_opportunity_trend": "价格机会趋势",
    "inventory_availability_trend": "库存可得性趋势",
    "opportunity_score": "Opportunity Score",
    "market_activity": "市场活跃度",
}


def format_eur(value: float | None) -> str:
    """Format an optional EUR value for business-facing display."""

    return "数据不足" if value is None else f"€{value:,.0f}"


def format_percentage(value: float | None, *, signed: bool = False) -> str:
    """Format an optional percentage without inventing missing values."""

    if value is None:
        return "数据不足"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:,.2f}%"


def format_index_score(index: QuantitativeIndex) -> str:
    """Format a quantitative model result without replacing missing values."""

    return "数据不足" if index.score is None else f"{index.score:.2f}"


def render_report_notice(report: DailyMarketIntelligence) -> None:
    """Show source, report date, and metric interpretation disclosure."""

    st.markdown(
        f"""
        <div class="data-provenance">
            <span><strong>数据日期</strong> {report.report_date.isoformat()}</span>
            <span><strong>来源</strong> Phase 5A Analytics Layer</span>
            <span><strong>口径</strong> 市场挂牌与活跃库存</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("挂牌价格不是实际成交价格，挂牌数量不代表真实销量。")


def render_intelligence_unavailable(message: str | None) -> None:
    """Render a friendly error when the analytics report cannot be loaded."""

    st.error(
        message or "Phase 5A 情报报告当前不可用，请先生成每日市场情报 JSON。",
        icon="⚠️",
    )
    st.code(
        ".\\.venv\\Scripts\\python.exe -m germania.analytics "
        "--database-path database\\project_germania_live.sqlite3 "
        "--output reports\\daily_market_intelligence.json",
        language="powershell",
    )


def vehicle_table_rows(
    vehicles: Iterable[VehicleIntelligence],
) -> list[dict[str, object]]:
    """Return Streamlit-ready vehicle table rows from dynamic report records."""

    return [
        {
            "品牌": item.brand,
            "车型": item.model,
            "机会分": item.opportunity_score.score,
            "活跃挂牌": item.metrics.active_listing_count,
            "平均挂牌价(EUR)": item.metrics.average_price_eur,
            "7日价格变化(%)": item.metrics.price_change_7d_pct,
            "30日价格变化(%)": item.metrics.price_change_30d_pct,
            "7日新增": item.metrics.new_listings_count_7d,
            "7日库存变化": item.metrics.inventory_change_7d_count,
        }
        for item in vehicles
    ]


def quantitative_table_rows(
    report: DailyMarketIntelligence,
) -> list[dict[str, object]]:
    """Return dynamic vehicle ranking rows with all explainable model outputs."""

    scores = report.quantitative_by_vehicle
    return [
        {
            "品牌": item.brand,
            "车型": item.model,
            "Opportunity Score": item.opportunity_score.score,
            "活跃挂牌": item.metrics.active_listing_count,
            "平均挂牌价(EUR)": item.metrics.average_price_eur,
            "7日价格变化(%)": item.metrics.price_change_7d_pct,
            "7日库存变化": item.metrics.inventory_change_7d_count,
            "Price Pressure": scores[
                vehicle_key(item.brand, item.model)
            ].price_pressure.score,
            "Inventory Pressure": scores[
                vehicle_key(item.brand, item.model)
            ].inventory_pressure.score,
            "Market Momentum": scores[
                vehicle_key(item.brand, item.model)
            ].market_momentum.score,
            "Momentum 状态": scores[
                vehicle_key(item.brand, item.model)
            ].market_momentum.label,
        }
        for item in report.vehicles
    ]


def render_quantitative_score_cards(
    scores: VehicleQuantitativeScores,
    *,
    show_explanation: bool = False,
) -> None:
    """Render responsive Phase 11 model cards and optional component evidence."""

    with st.container(horizontal=True):
        st.metric(
            "Price Pressure Index",
            format_index_score(scores.price_pressure),
            border=True,
            help="价格下降、库存增加和挂牌价离散度增强时，指数提高。",
        )
        st.metric(
            "Inventory Pressure Index",
            format_index_score(scores.inventory_pressure),
            border=True,
            help="相对库存、库存增长和新增挂牌增强而活跃度不足时，指数提高。",
        )
        st.metric(
            "Market Momentum Score",
            format_index_score(scores.market_momentum),
            border=True,
            help="买方机会视角的挂牌市场动能，不是销量或需求动能。",
        )
        with st.container(border=True, width="stretch"):
            st.caption("Momentum 状态")
            if scores.market_momentum.label is None:
                st.badge("Insufficient data", color="gray")
            else:
                st.badge(
                    scores.market_momentum.label,
                    color=_momentum_badge_color(scores.market_momentum.label),
                )
    if show_explanation:
        with st.expander(
            "查看三个指数的构成、权重与数据来源",
            icon=":material/function:",
        ):
            st.dataframe(
                _quantitative_component_rows(scores),
                hide_index=True,
                width="stretch",
                column_config={
                    "组件得分": st.column_config.NumberColumn(format="%.2f"),
                    "基础权重(%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "实际权重(%)": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
            st.caption(QUANTITATIVE_METHODOLOGY["scope"])
            st.json(QUANTITATIVE_METHODOLOGY)


def average_quantitative_score(
    report: DailyMarketIntelligence,
    index_name: str,
) -> tuple[float | None, int]:
    """Return an unweighted model mean and available-vehicle coverage count."""

    if index_name not in {
        "price_pressure",
        "inventory_pressure",
        "market_momentum",
    }:
        raise ValueError("unsupported quantitative index")
    values = [
        index.score
        for scores in report.quantitative_scores
        if (index := getattr(scores, index_name)).score is not None
    ]
    return (sum(values) / len(values), len(values)) if values else (None, 0)


def render_score_card(vehicle: VehicleIntelligence) -> None:
    """Render one transparent opportunity score with component disclosure."""

    component_labels = {
        "inventory_attractiveness": "库存吸引力",
        "price_competitiveness": "价格竞争力",
        "price_trend": "价格趋势",
        "market_activity": "市场活跃度",
    }
    components = vehicle.opportunity_score.components
    vehicle_name = f"{html.escape(vehicle.brand)} · {html.escape(vehicle.model)}"
    score_text = f"{vehicle.opportunity_score.score:.2f}"
    rows = []
    for key, label in component_labels.items():
        value = components.get(key)
        weight = vehicle.opportunity_score.applied_weights.get(key)
        rows.append(
            {
                "评分组件": label,
                "组件得分": value,
                "实际权重": f"{weight * 100:.2f}%" if weight is not None else "未采用",
            }
        )

    st.markdown(
        f"""
        <div class="score-panel">
            <div>
                <div class="score-label">VEHICLE OPPORTUNITY SCORE</div>
                <div class="score-title">{vehicle_name}</div>
            </div>
            <div class="score-value">{score_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(rows, hide_index=True, width="stretch")


def _quantitative_component_rows(
    scores: VehicleQuantitativeScores,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for model_name, index in (
        ("Price Pressure", scores.price_pressure),
        ("Inventory Pressure", scores.inventory_pressure),
        ("Market Momentum", scores.market_momentum),
    ):
        for component, value in index.components.items():
            rows.append(
                {
                    "模型": model_name,
                    "组件": _QUANTITATIVE_COMPONENT_LABELS.get(component, component),
                    "组件得分": value,
                    "基础权重(%)": index.weights[component] * 100,
                    "实际权重(%)": (
                        index.applied_weights.get(component, 0) * 100
                        if index.score is not None
                        else None
                    ),
                    "数据来源": index.component_sources[component],
                    "状态": index.status,
                }
            )
    return rows


def _momentum_badge_color(label: str) -> str:
    if label in {"Strong Positive", "Positive"}:
        return "green"
    if label == "Neutral":
        return "blue"
    if label == "Negative":
        return "orange"
    return "red"
