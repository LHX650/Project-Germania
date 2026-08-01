"""Reusable Streamlit views for transparent comparable-vehicle benchmarks."""

from __future__ import annotations

from typing import Any

import streamlit as st
from services.database import ComparableVehicleMetadata
from services.intelligence import (
    DailyMarketIntelligence,
    VehicleIntelligence,
    vehicle_key,
)
from services.peer_benchmarking import PeerBenchmarkReport

from germania.analytics.comparable_benchmarking import ComparableVehicleBenchmark

_METRIC_PRESENTATION = {
    "price_gap_pct": ("Average asking price", "EUR"),
    "inventory_gap_pct": ("Active listing inventory", "count"),
    "price_trend_gap_pp": ("7-day price trend", "%"),
    "opportunity_score_gap": ("Opportunity Score", "score"),
    "price_pressure_gap": ("Price Pressure", "score"),
    "inventory_pressure_gap": ("Inventory Pressure", "score"),
    "market_momentum_gap": ("Market Momentum", "score"),
}
_PEER_INSIGHT_TRANSLATIONS = {
    "\u6302\u724c\u5747\u4ef7\u4f4e\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Average asking price is below the peer median"
    ),
    "\u6302\u724c\u5747\u4ef7\u9ad8\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Average asking price is above the peer median"
    ),
    "7\u65e5\u4ef7\u683c\u8d8b\u52bf\u5f3a\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "7-day price trend is stronger than the peer median"
    ),
    "7\u65e5\u4ef7\u683c\u8d8b\u52bf\u5f31\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "7-day price trend is weaker than the peer median"
    ),
    "Opportunity Score \u9ad8\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Vehicle Opportunity Score is above the peer median"
    ),
    "Opportunity Score \u4f4e\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Vehicle Opportunity Score is below the peer median"
    ),
    "Price Pressure \u4f4e\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Price Pressure is below the peer median"
    ),
    "Price Pressure \u9ad8\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Price Pressure is above the peer median"
    ),
    "Inventory Pressure \u4f4e\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Inventory Pressure is below the peer median"
    ),
    "Inventory Pressure \u9ad8\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Inventory Pressure is above the peer median"
    ),
    "Market Momentum \u9ad8\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Market Momentum is above the peer median"
    ),
    "Market Momentum \u4f4e\u4e8e\u540c\u7c7b\u4e2d\u4f4d\u6570": (
        "Market Momentum is below the peer median"
    ),
}


def render_peer_comparison(
    peer_report: PeerBenchmarkReport,
    report: DailyMarketIntelligence,
    vehicle: VehicleIntelligence,
    *,
    chart_key: str,
) -> None:
    """Render the full Vehicle Analysis peer comparison experience."""

    key = vehicle_key(vehicle.brand, vehicle.model)
    benchmark = peer_report.by_vehicle.get(key)
    metadata = peer_report.metadata_by_vehicle.get(key)
    st.subheader("Peer Benchmark")
    if benchmark is None:
        st.info(
            "insufficient_data: no Peer Benchmark result matches the selected "
            "vehicle. Confirm that the Analytics vehicle key matches the SQLite "
            "canonical vehicle."
        )
        return
    if benchmark.status != "ok":
        with st.container(border=True):
            st.markdown("#### Peer Group")
            st.info(
                "insufficient_data: a Peer Group with at least two comparable "
                f"vehicles could not be established. Reason: "
                f"{benchmark.reason or 'insufficient control variables'}"
            )
            st.caption("Current controls: " + _control_text(metadata))
            st.caption(
                "Minimum requirements: a valid average asking price, vehicle "
                "segment, and powertrain, with at least two peers remaining after "
                "progressive relaxation."
            )
        return

    with st.container(border=True):
        st.markdown("#### Peer Group")
        with st.container(horizontal=True):
            st.metric("Peer count", f"{benchmark.sample_size}", border=True)
            st.metric(
                "Peer Rank",
                (
                    f"#{benchmark.peer_rank}/{benchmark.sample_size + 1}"
                    if benchmark.peer_rank is not None
                    else "insufficient_data"
                ),
                border=True,
            )
            st.metric(
                "Peer Percentile",
                (
                    f"{benchmark.peer_percentile:.2f}%"
                    if benchmark.peer_percentile is not None
                    else "insufficient_data"
                ),
                border=True,
            )
            st.metric("Match level", f"Level {benchmark.match_level}", border=True)
        st.caption("Target vehicle: " + key)
        st.caption(
            "Match basis: "
            + " · ".join(benchmark.match_basis)
            + " · Controls: "
            + _control_text(metadata)
        )
        st.write("**Peer vehicles:** " + ", ".join(benchmark.peer_keys))

    st.markdown("#### Peer Gap summary")
    _render_gap_metrics(benchmark)

    st.markdown("#### Target vs Peer Group")
    chart_metrics = (
        ("price_gap_pct", "inventory_gap_pct"),
        ("opportunity_score_gap", "market_momentum_gap"),
        ("price_pressure_gap", "inventory_pressure_gap"),
    )
    for metric_pair in chart_metrics:
        columns = st.columns(2)
        for column, metric in zip(columns, metric_pair, strict=True):
            with column:
                render_peer_metric_chart(
                    benchmark,
                    report,
                    metric,
                    chart_key=f"{chart_key}_{metric}",
                )

    st.markdown("#### Peer Median and rank details")
    st.dataframe(
        benchmark_metric_rows(benchmark),
        hide_index=True,
        width="stretch",
        column_config={
            "Target value": st.column_config.NumberColumn(format="%.2f"),
            "Peer median": st.column_config.NumberColumn(format="%.2f"),
            "Gap": st.column_config.NumberColumn(format="%+.2f"),
            "Percentile": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    _render_advantages_and_disadvantages(benchmark)
    st.caption(
        "The Peer Median is calculated from comparable vehicles only and excludes "
        "the target. Inventory means active listings, not sales; prices are asking "
        "prices, not transaction prices. Percentiles rank raw metric values, so a "
        "high pressure-index percentile indicates greater pressure, not superiority."
    )


def render_compact_peer_summary(
    peer_report: PeerBenchmarkReport,
    vehicle: VehicleIntelligence,
) -> None:
    """Render a compact peer disclosure for Vehicle Intelligence."""

    benchmark = peer_report.by_vehicle[vehicle_key(vehicle.brand, vehicle.model)]
    st.subheader("Peer Benchmarking")
    if benchmark.status != "ok":
        st.info(f"insufficient_data: {benchmark.reason}")
        return
    price = benchmark.metrics["price_gap_pct"]
    opportunity = benchmark.metrics["opportunity_score_gap"]
    momentum = benchmark.metrics["market_momentum_gap"]
    with st.container(horizontal=True):
        st.metric("Peer count", benchmark.sample_size, border=True)
        st.metric("Price gap", _format_gap(price.gap, "%"), border=True)
        st.metric("Opportunity Gap", _format_gap(opportunity.gap, " pts"), border=True)
        st.metric("Momentum Gap", _format_gap(momentum.gap, " pts"), border=True)
        st.metric(
            "Peer Percentile",
            (
                f"{benchmark.peer_percentile:.2f}%"
                if benchmark.peer_percentile is not None
                else "insufficient_data"
            ),
            border=True,
        )
    st.caption(
        f"Level {benchmark.match_level} · "
        + " · ".join(benchmark.match_basis)
        + f" · Peers: {', '.join(benchmark.peer_keys)}"
    )


def peer_overview_rows(
    peer_report: PeerBenchmarkReport,
    *,
    vehicle_keys: set[str] | None = None,
) -> list[dict[str, object]]:
    """Return comparable rows for peer-first tables on other Dashboard pages."""

    metadata = peer_report.metadata_by_vehicle
    rows = []
    for benchmark in peer_report.benchmarks:
        if vehicle_keys is not None and benchmark.vehicle_key not in vehicle_keys:
            continue
        controls = metadata.get(benchmark.vehicle_key)
        row: dict[str, object] = {
            "Vehicle": benchmark.vehicle_key,
            "Status": benchmark.status,
            "Segment": controls.vehicle_segment if controls else None,
            "Powertrain": controls.powertrain if controls else None,
            "Peer count": benchmark.sample_size,
            "Match level": benchmark.match_level,
            "Peer Rank": benchmark.peer_rank,
            "Peer Percentile(%)": benchmark.peer_percentile,
        }
        for metric in _METRIC_PRESENTATION:
            row[_METRIC_PRESENTATION[metric][0] + " Gap"] = (
                benchmark.metrics[metric].gap if benchmark.status == "ok" else None
            )
        rows.append(row)
    return rows


def benchmark_metric_rows(
    benchmark: ComparableVehicleBenchmark,
) -> list[dict[str, object]]:
    """Return target/median/gap/rank values for the peer comparison table."""

    return [
        {
            "Metric": label,
            "Target value": benchmark.metrics[metric].target_value,
            "Peer median": benchmark.metrics[metric].peer_median,
            "Gap": benchmark.metrics[metric].gap,
            "Gap unit": benchmark.metrics[metric].gap_unit,
            "Peer rank": benchmark.metrics[metric].rank,
            "Percentile": benchmark.metrics[metric].percentile,
            "Available peers": benchmark.metrics[metric].available_peer_count,
        }
        for metric, (label, _) in _METRIC_PRESENTATION.items()
    ]


def render_peer_metric_chart(
    benchmark: ComparableVehicleBenchmark,
    report: DailyMarketIntelligence,
    metric: str,
    *,
    chart_key: str,
) -> None:
    """Highlight the target and peer median in one dynamic Vega-Lite chart."""

    if metric not in _METRIC_PRESENTATION:
        raise ValueError("unsupported peer metric")
    values = []
    for key in (benchmark.vehicle_key, *benchmark.peer_keys):
        value = _vehicle_metric_value(report, key, metric)
        if value is not None:
            values.append(
                {
                    "vehicle": key,
                    "value": value,
                    "role": "Target" if key == benchmark.vehicle_key else "Peer",
                }
            )
    metric_benchmark = benchmark.metrics[metric]
    label, unit = _METRIC_PRESENTATION[metric]
    if not values or metric_benchmark.peer_median is None:
        with st.container(border=True):
            st.markdown(f"**{label} comparison**")
            st.info(
                f"insufficient_data: {label} lacks a target value or valid peer "
                f"values. Available peers: {metric_benchmark.available_peer_count}."
            )
        return
    spec: dict[str, Any] = {
        "height": 280,
        "layer": [
            {
                "data": {"values": values},
                "mark": {
                    "type": "bar",
                    "cornerRadiusTopLeft": 4,
                    "cornerRadiusTopRight": 4,
                },
                "encoding": {
                    "x": {
                        "field": "vehicle",
                        "type": "nominal",
                        "title": None,
                        "sort": "-y",
                        "axis": {"labelAngle": -25},
                    },
                    "y": {"field": "value", "type": "quantitative", "title": label},
                    "color": {
                        "condition": {
                            "test": "datum.role === 'Target'",
                            "value": "#e07a3f",
                        },
                        "value": "#376f93",
                    },
                    "tooltip": [
                        {"field": "vehicle", "type": "nominal", "title": "Vehicle"},
                        {"field": "role", "type": "nominal", "title": "Role"},
                        {
                            "field": "value",
                            "type": "quantitative",
                            "title": label,
                            "format": ",.2f",
                        },
                    ],
                },
            },
            {
                "data": {"values": [{"median": metric_benchmark.peer_median}]},
                "mark": {
                    "type": "rule",
                    "color": "#a55b23",
                    "strokeDash": [6, 4],
                    "strokeWidth": 2,
                },
                "encoding": {"y": {"field": "median", "type": "quantitative"}},
            },
        ],
    }
    with st.container(border=True):
        st.vega_lite_chart(spec, width="stretch", key=chart_key)
        st.caption(
            f"{label}: orange identifies the target vehicle; the dashed line marks "
            f"the Peer Median at {metric_benchmark.peer_median:,.2f} {unit}."
        )


def _vehicle_metric_value(
    report: DailyMarketIntelligence,
    key: str,
    metric: str,
) -> float | None:
    vehicles = {vehicle_key(item.brand, item.model): item for item in report.vehicles}
    vehicle = vehicles[key]
    scores = report.quantitative_by_vehicle[key]
    values = {
        "price_gap_pct": vehicle.metrics.average_price_eur,
        "inventory_gap_pct": float(vehicle.metrics.active_listing_count),
        "price_trend_gap_pp": vehicle.metrics.price_change_7d_pct,
        "opportunity_score_gap": vehicle.opportunity_score.score,
        "price_pressure_gap": scores.price_pressure.score,
        "inventory_pressure_gap": scores.inventory_pressure.score,
        "market_momentum_gap": scores.market_momentum.score,
    }
    return values[metric]


def _render_advantages_and_disadvantages(
    benchmark: ComparableVehicleBenchmark,
) -> None:
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**Key advantages**")
        if benchmark.advantages:
            for item in benchmark.advantages:
                st.success(_translate_peer_insight(item), icon=":material/trending_up:")
        else:
            st.info("No material peer advantage meets the published threshold.")
    with columns[1]:
        st.markdown("**Key disadvantages**")
        if benchmark.disadvantages:
            for item in benchmark.disadvantages:
                st.warning(
                    _translate_peer_insight(item), icon=":material/trending_down:"
                )
        else:
            st.info("No material peer disadvantage meets the published threshold.")


def _render_gap_metrics(benchmark: ComparableVehicleBenchmark) -> None:
    gaps = (
        ("Price Gap", "price_gap_pct", "%"),
        ("Inventory Gap", "inventory_gap_pct", "%"),
        ("Opportunity Gap", "opportunity_score_gap", " pts"),
        ("Price Pressure Gap", "price_pressure_gap", " pts"),
        ("Inventory Pressure Gap", "inventory_pressure_gap", " pts"),
        ("Momentum Gap", "market_momentum_gap", " pts"),
    )
    with st.container(horizontal=True):
        for label, metric, suffix in gaps:
            value = benchmark.metrics[metric]
            st.metric(
                label,
                _format_gap(value.gap, suffix),
                help=(
                    "Peer Median: insufficient_data"
                    if value.peer_median is None
                    else f"Peer Median: {value.peer_median:,.2f}"
                ),
                border=True,
            )


def _control_text(metadata: ComparableVehicleMetadata | None) -> str:
    if metadata is None:
        return "Segment missing · Powertrain missing · Body missing"
    return " · ".join(
        (
            f"Segment {metadata.vehicle_segment or 'missing'}",
            f"Powertrain {metadata.powertrain or 'missing'}",
            f"Body {metadata.body_type or 'missing'}",
            f"Market attribute {metadata.market_attribute or 'missing'}",
        )
    )


def _format_gap(value: float | None, suffix: str) -> str:
    return "insufficient_data" if value is None else f"{value:+.2f}{suffix}"


def _translate_peer_insight(value: str) -> str:
    """Translate known Analytics peer messages at the presentation boundary."""

    return _PEER_INSIGHT_TRANSLATIONS.get(value, value)
