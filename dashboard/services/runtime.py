"""Central, read-only runtime path selection for Dashboard data artifacts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEMO_MODE_ENV = "DEMO_MODE"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


class DashboardConfigurationError(ValueError):
    """Raised when a Dashboard runtime setting is invalid."""


@dataclass(frozen=True)
class DashboardDataPaths:
    """Resolved read-only paths for one Dashboard runtime mode."""

    demo_mode: bool
    data_root: Path
    database: Path
    market_intelligence: Path
    ai_market_report: Path
    external_intelligence: Path
    content_feed: Path
    strategic_market_report: Path
    pipeline_status: Path


def get_project_root() -> Path:
    """Return the absolute Project Germania repository root."""

    return Path(__file__).resolve().parents[2]


def demo_mode_enabled(value: str | bool | None = None) -> bool:
    """Return whether the Dashboard should use the bundled public demo data.

    An unset value defaults to ``False`` so existing production deployments keep
    their current database and report paths.
    """

    if isinstance(value, bool):
        return value
    raw_value = os.getenv(DEMO_MODE_ENV) if value is None else value
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise DashboardConfigurationError(
        f"{DEMO_MODE_ENV} must be one of: true, false, 1, 0, yes, no, on, off."
    )


def get_dashboard_data_paths(
    demo_mode: bool | None = None,
) -> DashboardDataPaths:
    """Resolve all Dashboard inputs without creating or modifying any file."""

    enabled = demo_mode_enabled() if demo_mode is None else demo_mode
    project_root = get_project_root()
    if enabled:
        data_root = project_root / "demo"
        return DashboardDataPaths(
            demo_mode=True,
            data_root=data_root,
            database=data_root / "project_germania_demo.sqlite3",
            market_intelligence=data_root / "daily_market_intelligence.json",
            ai_market_report=data_root / "daily_ai_market_report.md",
            external_intelligence=data_root / "external_intelligence.json",
            content_feed=data_root / "content_feed.json",
            strategic_market_report=data_root / "strategic_market_report.md",
            pipeline_status=data_root / "pipeline_status.json",
        )

    reports_root = project_root / "reports"
    return DashboardDataPaths(
        demo_mode=False,
        data_root=reports_root,
        database=project_root / "database" / "project_germania_live.sqlite3",
        market_intelligence=reports_root / "daily_market_intelligence.json",
        ai_market_report=reports_root / "daily_ai_market_report.md",
        external_intelligence=reports_root / "external_intelligence.json",
        content_feed=reports_root / "external_intelligence" / "content_feed.json",
        strategic_market_report=reports_root / "strategic_market_report.md",
        pipeline_status=reports_root / "pipeline_status.json",
    )
