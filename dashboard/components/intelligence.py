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
    "price_decline_7d": "7-day price decline pressure",
    "price_decline_30d": "30-day price decline pressure",
    "inventory_growth": "Inventory growth pressure",
    "price_dispersion": "Asking-price dispersion",
    "inventory_level": "Relative inventory level",
    "new_listing_intensity": "New-listing intensity",
    "low_market_activity": "Low market activity",
    "new_listing_activity": "New-listing activity",
    "price_opportunity_trend": "Price opportunity trend",
    "inventory_availability_trend": "Inventory availability trend",
    "opportunity_score": "Opportunity Score",
    "market_activity": "Market activity",
}


def format_eur(value: float | None) -> str:
    """Format an optional EUR value for business-facing display."""

    return "Insufficient data" if value is None else f"€{value:,.0f}"


def format_percentage(value: float | None, *, signed: bool = False) -> str:
    """Format an optional percentage without inventing missing values."""

    if value is None:
        return "Insufficient data"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:,.2f}%"


def format_index_score(index: QuantitativeIndex) -> str:
    """Format a quantitative model result without replacing missing values."""

    return "Insufficient data" if index.score is None else f"{index.score:.2f}"


def render_report_notice(report: DailyMarketIntelligence) -> None:
    """Show source, report date, and metric interpretation disclosure."""

    st.markdown(
        f"""
        <div class="data-provenance">
            <span><strong>Data date</strong> {report.report_date.isoformat()}</span>
            <span><strong>Source</strong> Phase 5A Analytics Layer</span>
            <span><strong>Scope</strong> Asking prices and active listings</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Asking prices are not transaction prices, and listing counts do not "
        "represent vehicle sales."
    )


def render_intelligence_unavailable(message: str | None) -> None:
    """Render a friendly error when the analytics report cannot be loaded."""

    st.error(
        message
        or "The Phase 5A intelligence report is unavailable. Generate the daily "
        "market intelligence JSON before opening this page.",
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
            "Brand": item.brand,
            "Vehicle": item.model,
            "Vehicle Opportunity Score": item.opportunity_score.score,
            "Active listings": item.metrics.active_listing_count,
            "Average asking price (EUR)": item.metrics.average_price_eur,
            "7-day price change (%)": item.metrics.price_change_7d_pct,
            "30-day price change (%)": item.metrics.price_change_30d_pct,
            "New listings (7 days)": item.metrics.new_listings_count_7d,
            "Inventory change (7 days)": item.metrics.inventory_change_7d_count,
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
            "Brand": item.brand,
            "Vehicle": item.model,
            "Opportunity Score": item.opportunity_score.score,
            "Active listings": item.metrics.active_listing_count,
            "Average asking price (EUR)": item.metrics.average_price_eur,
            "7-day price change (%)": item.metrics.price_change_7d_pct,
            "Inventory change (7 days)": item.metrics.inventory_change_7d_count,
            "Price Pressure": scores[
                vehicle_key(item.brand, item.model)
            ].price_pressure.score,
            "Inventory Pressure": scores[
                vehicle_key(item.brand, item.model)
            ].inventory_pressure.score,
            "Market Momentum": scores[
                vehicle_key(item.brand, item.model)
            ].market_momentum.score,
            "Momentum status": scores[
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
            help=(
                "The index rises when asking prices decline, inventory expands, "
                "and asking-price dispersion increases."
            ),
        )
        st.metric(
            "Inventory Pressure Index",
            format_index_score(scores.inventory_pressure),
            border=True,
            help=(
                "The index rises with elevated relative inventory, inventory "
                "growth, and new-listing intensity when market activity is weak."
            ),
        )
        st.metric(
            "Market Momentum Score",
            format_index_score(scores.market_momentum),
            border=True,
            help=(
                "A buyer-opportunity view of listing-market momentum; it is not "
                "sales or demand momentum."
            ),
        )
        with st.container(border=True, width="stretch"):
            st.caption("Momentum status")
            if scores.market_momentum.label is None:
                st.badge("Insufficient data", color="gray")
            else:
                st.badge(
                    scores.market_momentum.label,
                    color=_momentum_badge_color(scores.market_momentum.label),
                )
    if show_explanation:
        with st.expander(
            "View index components, weights, and data sources",
            icon=":material/function:",
        ):
            st.dataframe(
                _quantitative_component_rows(scores),
                hide_index=True,
                width="stretch",
                column_config={
                    "Component score": st.column_config.NumberColumn(format="%.2f"),
                    "Base weight (%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "Applied weight (%)": st.column_config.NumberColumn(
                        format="%.2f%%"
                    ),
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
        "inventory_attractiveness": "Inventory attractiveness",
        "price_competitiveness": "Price competitiveness",
        "price_trend": "Price trend",
        "market_activity": "Market activity",
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
                "Score component": label,
                "Component score": value,
                "Applied weight": (
                    f"{weight * 100:.2f}%" if weight is not None else "Not applied"
                ),
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
                    "Model": model_name,
                    "Component": _QUANTITATIVE_COMPONENT_LABELS.get(
                        component, component
                    ),
                    "Component score": value,
                    "Base weight (%)": index.weights[component] * 100,
                    "Applied weight (%)": (
                        index.applied_weights.get(component, 0) * 100
                        if index.score is not None
                        else None
                    ),
                    "Data source": index.component_sources[component],
                    "Status": index.status,
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
