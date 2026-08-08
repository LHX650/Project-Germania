"""Read-only early-warning rules over existing market intelligence metrics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from germania.analytics.comparable_benchmarking import ComparableVehicleBenchmark
from services.intelligence import (
    DailyMarketIntelligence,
    IntelligenceReportError,
    load_daily_market_intelligence,
    vehicle_key,
)
from services.peer_benchmarking import PeerBenchmarkReport, load_peer_benchmarks
from services.runtime import get_dashboard_data_paths

AlertLevel = Literal["Critical", "Warning", "Normal"]
AlertStatus = Literal["available", "insufficient_data"]
AlertImpact = Literal["risk", "opportunity", "stable", "unknown"]
AlertType = Literal[
    "Price Drop Alert",
    "Inventory Pressure Alert",
    "Peer Competitive Alert",
    "Opportunity Change Alert",
]

PRICE_DROP_THRESHOLDS = {
    "warning_change_pct": -3.0,
    "warning_pressure": 60.0,
    "critical_change_pct": -7.0,
    "critical_pressure": 70.0,
}
INVENTORY_PRESSURE_THRESHOLDS = {
    "warning_change_pct": 15.0,
    "warning_pressure": 60.0,
    "critical_change_pct": 30.0,
    "critical_pressure": 70.0,
}
PEER_CHANGE_THRESHOLDS = {
    "warning_percentile_points": 10.0,
    "critical_percentile_points": 25.0,
    "warning_rank_places": 1,
    "critical_rank_places": 2,
    "negative_momentum": 40.0,
}
OPPORTUNITY_CHANGE_THRESHOLDS = {
    "warning_points": 8.0,
    "critical_points": 15.0,
    "negative_momentum": 40.0,
}


@dataclass(frozen=True)
class MarketAlert:
    """One transparent rule evaluation for a vehicle and report date."""

    alert_type: AlertType
    level: AlertLevel | None
    status: AlertStatus
    impact: AlertImpact
    brand: str
    vehicle: str
    trigger_reason: str
    related_metrics: dict[str, float | int | str | None]
    timestamp: datetime
    missing_inputs: tuple[str, ...] = ()

    @property
    def vehicle_key(self) -> str:
        """Return the canonical Dashboard vehicle identity."""

        return vehicle_key(self.brand, self.vehicle)


@dataclass(frozen=True)
class AlertTrendPoint:
    """Daily counts of rule evaluations by alert level."""

    alert_date: date
    critical_count: int
    warning_count: int
    normal_count: int
    insufficient_data_count: int


@dataclass(frozen=True)
class MarketAlertReport:
    """Current alerts plus an archive-backed historical alert trend."""

    report_date: date
    alerts: tuple[MarketAlert, ...]
    trend: tuple[AlertTrendPoint, ...]
    limitations: tuple[str, ...]

    @property
    def critical_count(self) -> int:
        """Return current Critical rule evaluations."""

        return sum(item.level == "Critical" for item in self.alerts)

    @property
    def warning_count(self) -> int:
        """Return current Warning rule evaluations."""

        return sum(item.level == "Warning" for item in self.alerts)

    @property
    def normal_count(self) -> int:
        """Return current Normal rule evaluations."""

        return sum(item.level == "Normal" for item in self.alerts)

    @property
    def insufficient_data_count(self) -> int:
        """Return current evaluations that could not be completed."""

        return sum(item.status == "insufficient_data" for item in self.alerts)


def load_market_alert_report(
    current_report: DailyMarketIntelligence,
    *,
    database_path: str | Path | None = None,
    history_root: str | Path | None = None,
) -> MarketAlertReport:
    """Load archived Analytics read-only and evaluate the existing alert rules."""

    paths = get_dashboard_data_paths()
    resolved_database = Path(database_path) if database_path else paths.database
    resolved_history_root = (
        Path(history_root) if history_root is not None else paths.data_root / "archive"
    )
    reports, history_limitations = _load_history(
        current_report,
        resolved_history_root,
    )
    peer_reports: dict[date, PeerBenchmarkReport] = {}
    limitations = list(history_limitations)
    for report in reports:
        try:
            peer_reports[report.report_date] = load_peer_benchmarks(
                report,
                resolved_database,
            )
        except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
            limitations.append(
                f"Peer Benchmark unavailable for {report.report_date}: {exc}"
            )
    return build_market_alert_report(
        current_report,
        history=reports,
        peer_reports=peer_reports,
        limitations=tuple(limitations),
    )


def build_market_alert_report(
    current_report: DailyMarketIntelligence,
    *,
    history: tuple[DailyMarketIntelligence, ...] = (),
    peer_reports: dict[date, PeerBenchmarkReport] | None = None,
    limitations: tuple[str, ...] = (),
) -> MarketAlertReport:
    """Evaluate alert rules without changing any underlying quantitative model."""

    reports_by_date = {
        report.report_date: report
        for report in history
        if report.report_date <= current_report.report_date
    }
    reports_by_date[current_report.report_date] = current_report
    reports = tuple(reports_by_date[key] for key in sorted(reports_by_date))
    peers = peer_reports or {}
    alerts_by_date: dict[date, tuple[MarketAlert, ...]] = {}
    for index, report in enumerate(reports):
        previous = reports[index - 1] if index else None
        alerts_by_date[report.report_date] = evaluate_market_alerts(
            report,
            previous_report=previous,
            peer_report=peers.get(report.report_date),
            previous_peer_report=(
                peers.get(previous.report_date) if previous is not None else None
            ),
        )
    trend = tuple(
        _trend_point(report_date, alerts)
        for report_date, alerts in alerts_by_date.items()
    )
    return MarketAlertReport(
        report_date=current_report.report_date,
        alerts=alerts_by_date[current_report.report_date],
        trend=trend,
        limitations=limitations,
    )


def evaluate_market_alerts(
    report: DailyMarketIntelligence,
    *,
    previous_report: DailyMarketIntelligence | None = None,
    peer_report: PeerBenchmarkReport | None = None,
    previous_peer_report: PeerBenchmarkReport | None = None,
) -> tuple[MarketAlert, ...]:
    """Evaluate four alert rules for every dynamic vehicle in a daily report."""

    previous_vehicles = (
        {vehicle_key(item.brand, item.model): item for item in previous_report.vehicles}
        if previous_report is not None
        else {}
    )
    current_peers = peer_report.by_vehicle if peer_report is not None else {}
    previous_peers = (
        previous_peer_report.by_vehicle if previous_peer_report is not None else {}
    )
    timestamp = datetime.combine(report.report_date, time.min, tzinfo=UTC)
    alerts: list[MarketAlert] = []
    for vehicle in report.vehicles:
        key = vehicle_key(vehicle.brand, vehicle.model)
        quantitative = report.quantitative_by_vehicle[key]
        momentum = quantitative.market_momentum.score
        alerts.extend(
            (
                _price_drop_alert(
                    vehicle.brand,
                    vehicle.model,
                    vehicle.metrics.price_change_7d_pct,
                    quantitative.price_pressure.score,
                    momentum,
                    timestamp,
                ),
                _inventory_pressure_alert(
                    vehicle.brand,
                    vehicle.model,
                    vehicle.metrics.inventory_change_7d_pct,
                    quantitative.inventory_pressure.score,
                    momentum,
                    timestamp,
                ),
                _peer_competitive_alert(
                    vehicle.brand,
                    vehicle.model,
                    current_peers.get(key),
                    previous_peers.get(key),
                    momentum,
                    timestamp,
                ),
                _opportunity_change_alert(
                    vehicle.brand,
                    vehicle.model,
                    vehicle.opportunity_score.score,
                    (
                        previous_vehicles[key].opportunity_score.score
                        if key in previous_vehicles
                        else None
                    ),
                    momentum,
                    timestamp,
                ),
            )
        )
    return tuple(alerts)


def _price_drop_alert(
    brand: str,
    model: str,
    price_change: float | None,
    price_pressure: float | None,
    momentum: float | None,
    timestamp: datetime,
) -> MarketAlert:
    metrics = {
        "price_change_7d_pct": price_change,
        "price_pressure_index": price_pressure,
        "market_momentum": momentum,
    }
    missing = _missing(metrics, ("price_change_7d_pct", "price_pressure_index"))
    if missing:
        return _insufficient(
            "Price Drop Alert", brand, model, metrics, timestamp, missing
        )
    assert price_change is not None and price_pressure is not None
    if (
        price_change <= PRICE_DROP_THRESHOLDS["critical_change_pct"]
        and price_pressure >= PRICE_DROP_THRESHOLDS["critical_pressure"]
    ):
        level: AlertLevel = "Critical"
    elif (
        price_change <= PRICE_DROP_THRESHOLDS["warning_change_pct"]
        and price_pressure >= PRICE_DROP_THRESHOLDS["warning_pressure"]
    ):
        level = "Warning"
    else:
        level = "Normal"
    reason = (
        f"7-day asking price changed {price_change:+.2f}% while Price Pressure "
        f"was {price_pressure:.2f}."
    )
    return _available(
        "Price Drop Alert",
        level,
        "risk" if level != "Normal" else "stable",
        brand,
        model,
        reason,
        metrics,
        timestamp,
    )


def _inventory_pressure_alert(
    brand: str,
    model: str,
    inventory_change: float | None,
    inventory_pressure: float | None,
    momentum: float | None,
    timestamp: datetime,
) -> MarketAlert:
    metrics = {
        "inventory_change_7d_pct": inventory_change,
        "inventory_pressure_index": inventory_pressure,
        "market_momentum": momentum,
    }
    missing = _missing(
        metrics,
        ("inventory_change_7d_pct", "inventory_pressure_index"),
    )
    if missing:
        return _insufficient(
            "Inventory Pressure Alert", brand, model, metrics, timestamp, missing
        )
    assert inventory_change is not None and inventory_pressure is not None
    if (
        inventory_change >= INVENTORY_PRESSURE_THRESHOLDS["critical_change_pct"]
        and inventory_pressure >= INVENTORY_PRESSURE_THRESHOLDS["critical_pressure"]
    ):
        level: AlertLevel = "Critical"
    elif (
        inventory_change >= INVENTORY_PRESSURE_THRESHOLDS["warning_change_pct"]
        and inventory_pressure >= INVENTORY_PRESSURE_THRESHOLDS["warning_pressure"]
    ):
        level = "Warning"
    else:
        level = "Normal"
    reason = (
        f"7-day listing inventory changed {inventory_change:+.2f}% while "
        f"Inventory Pressure was {inventory_pressure:.2f}."
    )
    return _available(
        "Inventory Pressure Alert",
        level,
        "risk" if level != "Normal" else "stable",
        brand,
        model,
        reason,
        metrics,
        timestamp,
    )


def _peer_competitive_alert(
    brand: str,
    model: str,
    current: ComparableVehicleBenchmark | None,
    previous: ComparableVehicleBenchmark | None,
    momentum: float | None,
    timestamp: datetime,
) -> MarketAlert:
    current_percentile = getattr(current, "peer_percentile", None)
    previous_percentile = getattr(previous, "peer_percentile", None)
    current_rank = getattr(current, "peer_rank", None)
    previous_rank = getattr(previous, "peer_rank", None)
    metrics = {
        "peer_percentile": current_percentile,
        "previous_peer_percentile": previous_percentile,
        "peer_rank": current_rank,
        "previous_peer_rank": previous_rank,
        "market_momentum": momentum,
    }
    missing = _missing(
        metrics,
        (
            "peer_percentile",
            "previous_peer_percentile",
            "peer_rank",
            "previous_peer_rank",
        ),
    )
    if current is not None and current.status != "ok":
        missing = (*missing, "current_peer_group")
    if previous is not None and previous.status != "ok":
        missing = (*missing, "previous_peer_group")
    if missing:
        return _insufficient(
            "Peer Competitive Alert",
            brand,
            model,
            metrics,
            timestamp,
            tuple(dict.fromkeys(missing)),
        )
    percentile_delta = float(current_percentile) - float(previous_percentile)
    rank_delta = int(current_rank) - int(previous_rank)
    metrics["peer_percentile_change_pp"] = percentile_delta
    metrics["peer_rank_change"] = rank_delta
    critical_decline = (
        (
            percentile_delta <= -PEER_CHANGE_THRESHOLDS["critical_percentile_points"]
            or rank_delta >= PEER_CHANGE_THRESHOLDS["critical_rank_places"]
        )
        and momentum is not None
        and momentum < PEER_CHANGE_THRESHOLDS["negative_momentum"]
    )
    warning_decline = (
        percentile_delta <= -PEER_CHANGE_THRESHOLDS["warning_percentile_points"]
        or rank_delta >= PEER_CHANGE_THRESHOLDS["warning_rank_places"]
    )
    material_improvement = (
        percentile_delta >= PEER_CHANGE_THRESHOLDS["warning_percentile_points"]
        or rank_delta <= -PEER_CHANGE_THRESHOLDS["warning_rank_places"]
    )
    if critical_decline:
        level: AlertLevel = "Critical"
        impact: AlertImpact = "risk"
    elif warning_decline:
        level = "Warning"
        impact = "risk"
    elif material_improvement:
        level = "Warning"
        impact = "opportunity"
    else:
        level = "Normal"
        impact = "stable"
    reason = (
        f"Peer percentile changed {percentile_delta:+.2f} points and peer rank "
        f"changed {rank_delta:+d} place(s)."
    )
    return _available(
        "Peer Competitive Alert",
        level,
        impact,
        brand,
        model,
        reason,
        metrics,
        timestamp,
    )


def _opportunity_change_alert(
    brand: str,
    model: str,
    current_score: float | None,
    previous_score: float | None,
    momentum: float | None,
    timestamp: datetime,
) -> MarketAlert:
    metrics = {
        "opportunity_score": current_score,
        "previous_opportunity_score": previous_score,
        "market_momentum": momentum,
    }
    missing = _missing(
        metrics,
        ("opportunity_score", "previous_opportunity_score"),
    )
    if missing:
        return _insufficient(
            "Opportunity Change Alert", brand, model, metrics, timestamp, missing
        )
    assert current_score is not None and previous_score is not None
    change = current_score - previous_score
    metrics["opportunity_score_change"] = change
    critical_decline = (
        change <= -OPPORTUNITY_CHANGE_THRESHOLDS["critical_points"]
        and momentum is not None
        and momentum < OPPORTUNITY_CHANGE_THRESHOLDS["negative_momentum"]
    )
    if critical_decline:
        level: AlertLevel = "Critical"
        impact: AlertImpact = "risk"
    elif change <= -OPPORTUNITY_CHANGE_THRESHOLDS["warning_points"]:
        level = "Warning"
        impact = "risk"
    elif change >= OPPORTUNITY_CHANGE_THRESHOLDS["warning_points"]:
        level = "Warning"
        impact = "opportunity"
    else:
        level = "Normal"
        impact = "stable"
    reason = f"Vehicle Opportunity Score changed {change:+.2f} points."
    return _available(
        "Opportunity Change Alert",
        level,
        impact,
        brand,
        model,
        reason,
        metrics,
        timestamp,
    )


def _available(
    alert_type: AlertType,
    level: AlertLevel,
    impact: AlertImpact,
    brand: str,
    model: str,
    reason: str,
    metrics: dict[str, float | int | str | None],
    timestamp: datetime,
) -> MarketAlert:
    return MarketAlert(
        alert_type=alert_type,
        level=level,
        status="available",
        impact=impact,
        brand=brand,
        vehicle=model,
        trigger_reason=reason,
        related_metrics=metrics,
        timestamp=timestamp,
    )


def _insufficient(
    alert_type: AlertType,
    brand: str,
    model: str,
    metrics: dict[str, float | int | str | None],
    timestamp: datetime,
    missing: tuple[str, ...],
) -> MarketAlert:
    return MarketAlert(
        alert_type=alert_type,
        level=None,
        status="insufficient_data",
        impact="unknown",
        brand=brand,
        vehicle=model,
        trigger_reason=("insufficient_data: missing " + ", ".join(missing)),
        related_metrics=metrics,
        timestamp=timestamp,
        missing_inputs=missing,
    )


def _missing(
    metrics: dict[str, float | int | str | None],
    required: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(name for name in required if metrics.get(name) is None)


def _trend_point(
    alert_date: date,
    alerts: tuple[MarketAlert, ...],
) -> AlertTrendPoint:
    return AlertTrendPoint(
        alert_date=alert_date,
        critical_count=sum(item.level == "Critical" for item in alerts),
        warning_count=sum(item.level == "Warning" for item in alerts),
        normal_count=sum(item.level == "Normal" for item in alerts),
        insufficient_data_count=sum(
            item.status == "insufficient_data" for item in alerts
        ),
    )


def _load_history(
    current_report: DailyMarketIntelligence,
    history_root: Path,
) -> tuple[tuple[DailyMarketIntelligence, ...], tuple[str, ...]]:
    if not history_root.is_dir():
        return (current_report,), (
            "Historical Analytics archive is unavailable; change-based alerts "
            "and trend history may be insufficient_data.",
        )
    candidates = sorted(
        history_root.glob("*/daily_market_intelligence.json"),
        key=lambda path: path.parent.name,
    )
    reports_by_date: dict[date, DailyMarketIntelligence] = {}
    limitations: list[str] = []
    for path in candidates:
        try:
            report = load_daily_market_intelligence(path)
        except IntelligenceReportError as exc:
            limitations.append(f"Skipped invalid Analytics archive {path.name}: {exc}")
            continue
        if report.report_date <= current_report.report_date:
            reports_by_date[report.report_date] = report
    reports_by_date[current_report.report_date] = current_report
    first_date = current_report.report_date - timedelta(days=29)
    reports = tuple(
        reports_by_date[key] for key in sorted(reports_by_date) if key >= first_date
    )
    return reports, tuple(limitations)
