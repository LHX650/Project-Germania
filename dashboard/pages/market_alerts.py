"""Active market early-warning page backed by existing Analytics signals."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

import streamlit as st
from components.ai_intelligence import render_alert_explainer
from components.intelligence import (
    render_intelligence_unavailable,
    render_report_notice,
)
from components.page_header import render_page_header
from services.intelligence import DailyMarketIntelligence
from services.market_alerts import (
    INVENTORY_PRESSURE_THRESHOLDS,
    OPPORTUNITY_CHANGE_THRESHOLDS,
    PEER_CHANGE_THRESHOLDS,
    PRICE_DROP_THRESHOLDS,
    MarketAlert,
    MarketAlertReport,
    load_market_alert_report,
)

_LEVEL_ORDER = {"Critical": 0, "Warning": 1, "Normal": 2, None: 3}


def render(
    report: DailyMarketIntelligence | None,
    error_message: str | None = None,
) -> None:
    """Render current alerts, vehicle risk ranking, and historical trends."""

    render_page_header(
        title="Market Alerts",
        subtitle=(
            "Monitor unusual asking-price, listing-inventory, peer-position, and "
            "Vehicle Opportunity Score changes using existing intelligence models."
        ),
    )
    if report is None:
        render_intelligence_unavailable(error_message)
        return
    render_report_notice(report)
    if not report.vehicles:
        st.info("insufficient_data: the current Analytics report has no vehicles.")
        return

    try:
        alert_report = load_market_alert_report(report)
    except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
        st.error(f"Market Alerts are unavailable: {exc}")
        return

    _render_summary(alert_report)
    filtered = _render_filters(alert_report)
    _render_alert_ranking(filtered)
    render_alert_explainer(report, alert_report)
    _render_vehicle_risk_ranking(alert_report)
    _render_historical_trend(alert_report)
    _render_methodology(alert_report)


def _render_summary(report: MarketAlertReport) -> None:
    st.subheader("Alert Summary")
    vehicles = {item.vehicle_key for item in report.alerts}
    with st.container(horizontal=True):
        st.metric("Critical", f"{report.critical_count:,}", border=True)
        st.metric("Warning", f"{report.warning_count:,}", border=True)
        st.metric("Normal", f"{report.normal_count:,}", border=True)
        st.metric(
            "Insufficient data",
            f"{report.insufficient_data_count:,}",
            border=True,
        )
        st.metric("Vehicles monitored", f"{len(vehicles):,}", border=True)
    if report.critical_count == 0 and report.warning_count == 0:
        st.success("No abnormal vehicle signals crossed the current alert rules.")
    st.caption(
        "Counts represent rule evaluations, not sales events. Asking-price and "
        "listing-inventory signals must not be interpreted as transaction prices "
        "or vehicle sales."
    )


def _render_filters(report: MarketAlertReport) -> tuple[MarketAlert, ...]:
    brands = sorted({item.brand for item in report.alerts})
    with st.container(horizontal=True):
        view = st.selectbox(
            "Alert view",
            ("Active alerts", "All evaluations", "Insufficient data"),
            key="market_alerts_view",
        )
        selected_brand = st.selectbox(
            "Brand",
            ("All brands", *brands),
            key="market_alerts_brand",
        )
        selected_type = st.selectbox(
            "Alert type",
            ("All alert types", *(sorted({item.alert_type for item in report.alerts}))),
            key="market_alerts_type",
        )
    filtered = report.alerts
    if view == "Active alerts":
        filtered = tuple(
            item for item in filtered if item.level in {"Critical", "Warning"}
        )
    elif view == "Insufficient data":
        filtered = tuple(
            item for item in filtered if item.status == "insufficient_data"
        )
    if selected_brand != "All brands":
        filtered = tuple(item for item in filtered if item.brand == selected_brand)
    if selected_type != "All alert types":
        filtered = tuple(item for item in filtered if item.alert_type == selected_type)
    return tuple(
        sorted(
            filtered,
            key=lambda item: (
                _LEVEL_ORDER[item.level],
                item.brand.casefold(),
                item.vehicle.casefold(),
                item.alert_type,
            ),
        )
    )


def _render_alert_ranking(alerts: tuple[MarketAlert, ...]) -> None:
    st.subheader("Alert Ranking")
    if not alerts:
        st.info("No alert evaluations match the selected filters.")
        return
    rows = [
        {
            "Alert Level": item.level or "insufficient_data",
            "Impact": item.impact.title(),
            "Vehicle": item.vehicle,
            "Brand": item.brand,
            "Alert": item.alert_type,
            "Trigger Reason": item.trigger_reason,
            "Related Metrics": _format_related_metrics(item),
            "Timestamp": item.timestamp,
        }
        for item in alerts
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        height=520,
        column_config={
            "Timestamp": st.column_config.DatetimeColumn(
                "Timestamp",
                format="YYYY-MM-DD HH:mm [UTC]",
            ),
        },
    )


def _render_vehicle_risk_ranking(report: MarketAlertReport) -> None:
    st.subheader("Vehicle Risk Ranking")
    grouped: dict[str, list[MarketAlert]] = defaultdict(list)
    for alert in report.alerts:
        grouped[alert.vehicle_key].append(alert)
    rows = []
    for alerts in grouped.values():
        risk_alerts = [
            item
            for item in alerts
            if item.impact == "risk" and item.level in {"Critical", "Warning"}
        ]
        critical = sum(item.level == "Critical" for item in risk_alerts)
        warning = sum(item.level == "Warning" for item in risk_alerts)
        level = "Critical" if critical else "Warning" if warning else "Normal"
        first = alerts[0]
        rows.append(
            {
                "Risk Level": level,
                "Vehicle": first.vehicle,
                "Brand": first.brand,
                "Critical Alerts": critical,
                "Warnings": warning,
                "Risk Triggers": "; ".join(item.alert_type for item in risk_alerts)
                or "No risk rule threshold crossed",
                "Data Status": (
                    "insufficient_data"
                    if all(item.status == "insufficient_data" for item in alerts)
                    else "available"
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            _LEVEL_ORDER[str(row["Risk Level"])],
            -int(row["Critical Alerts"]),
            -int(row["Warnings"]),
            str(row["Brand"]),
            str(row["Vehicle"]),
        )
    )
    st.dataframe(rows, hide_index=True, width="stretch", height=470)
    st.caption(
        "Ranking is an ordinal sort by Critical and Warning rule counts; it is "
        "not a new risk score or a replacement for Vehicle Opportunity Score."
    )


def _render_historical_trend(report: MarketAlertReport) -> None:
    st.subheader("Historical Alert Trend")
    if len(report.trend) < 2:
        st.info(
            "insufficient_data: at least two dated Analytics reports are required "
            "for a historical alert trend."
        )
        return
    rows = [
        {
            "Date": point.alert_date,
            "Critical": point.critical_count,
            "Warning": point.warning_count,
            "Normal": point.normal_count,
            "Insufficient data": point.insufficient_data_count,
        }
        for point in report.trend
    ]
    st.line_chart(
        rows,
        x="Date",
        y=("Critical", "Warning", "Normal", "Insufficient data"),
        height=330,
    )
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_methodology(report: MarketAlertReport) -> None:
    with st.expander("Alert rules and data coverage"):
        st.markdown(f"""
            - **Price Drop Alert:** Warning at 7-day asking-price change ≤
              {PRICE_DROP_THRESHOLDS['warning_change_pct']:.0f}% and Price Pressure
              ≥ {PRICE_DROP_THRESHOLDS['warning_pressure']:.0f}; Critical at ≤
              {PRICE_DROP_THRESHOLDS['critical_change_pct']:.0f}% and ≥
              {PRICE_DROP_THRESHOLDS['critical_pressure']:.0f}.
            - **Inventory Pressure Alert:** Warning at 7-day inventory change ≥
              {INVENTORY_PRESSURE_THRESHOLDS['warning_change_pct']:.0f}% and
              Inventory Pressure ≥
              {INVENTORY_PRESSURE_THRESHOLDS['warning_pressure']:.0f}; Critical at
              ≥ {INVENTORY_PRESSURE_THRESHOLDS['critical_change_pct']:.0f}% and ≥
              {INVENTORY_PRESSURE_THRESHOLDS['critical_pressure']:.0f}.
            - **Peer Competitive Alert:** Warning when peer percentile declines by
              at least {PEER_CHANGE_THRESHOLDS['warning_percentile_points']:.0f}
              points or rank worsens by at least
              {PEER_CHANGE_THRESHOLDS['warning_rank_places']} place; a larger decline
              becomes Critical only when Market Momentum is below
              {PEER_CHANGE_THRESHOLDS['negative_momentum']:.0f}.
            - **Opportunity Change Alert:** Warning at an absolute Vehicle
              Opportunity Score change of at least
              {OPPORTUNITY_CHANGE_THRESHOLDS['warning_points']:.0f} points; a decline
              of at least {OPPORTUNITY_CHANGE_THRESHOLDS['critical_points']:.0f}
              points becomes Critical only when Market Momentum is below
              {OPPORTUNITY_CHANGE_THRESHOLDS['negative_momentum']:.0f}.
            """)
        st.caption(
            "These are transparent threshold rules over existing models. Missing "
            "inputs are not imputed and return insufficient_data."
        )
        for limitation in report.limitations:
            st.info(limitation)


def _format_related_metrics(alert: MarketAlert) -> str:
    values = []
    for name, value in alert.related_metrics.items():
        label = name.replace("_", " ")
        if value is None:
            formatted = "insufficient_data"
        elif isinstance(value, float):
            formatted = f"{value:.2f}"
        else:
            formatted = str(value)
        values.append(f"{label}: {formatted}")
    return " | ".join(values)
