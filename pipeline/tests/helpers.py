"""Local artifacts and deterministic clocks for pipeline tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


class StepClock:
    """Return a new deterministic UTC second for each orchestration event."""

    def __init__(self) -> None:
        self.current = datetime(2026, 7, 31, 18, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


def write_analytics(path: Path) -> Path:
    """Write one minimal valid Phase 5A report."""

    payload = {
        "date": "2026-07-31",
        "vehicles": [
            {
                "vehicle": {"brand": "Dynamic Motors", "model": "Alpha"},
                "metrics": {
                    "active_listing_count": 10,
                    "average_price_eur": 30_000,
                    "minimum_price_eur": 25_000,
                    "maximum_price_eur": 35_000,
                    "price_change_7d_pct": -2.0,
                    "price_change_30d_pct": None,
                    "new_listings_count_7d": 4,
                    "inventory_change_7d_count": 2,
                    "inventory_change_7d_pct": 25.0,
                },
                "opportunity_score": {
                    "score": 82.5,
                    "components": {
                        "inventory_attractiveness": 80.0,
                        "price_competitiveness": 75.0,
                        "price_trend": 60.0,
                        "market_activity": 95.0,
                    },
                    "applied_weights": {
                        "inventory_attractiveness": 0.3,
                        "price_competitiveness": 0.3,
                        "price_trend": 0.2,
                        "market_activity": 0.2,
                    },
                },
            }
        ],
        "brands": [
            {
                "brand": "Dynamic Motors",
                "metrics": {
                    "active_inventory_count": 10,
                    "active_inventory_rank": 1,
                    "average_vehicle_price_eur": 30_000,
                    "bev_share_pct": 100.0,
                    "phev_share_pct": 0.0,
                    "bev_phev_share_pct": 100.0,
                    "model_coverage_count": 1,
                    "catalog_model_count": 1,
                    "model_coverage_pct": 100.0,
                },
            }
        ],
        "methodology": {"scope": "pipeline fixture"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def daily_summary(
    *,
    collection_status: str = "completed",
    analytics_status: str = "completed",
) -> str:
    """Return an unchanged-daily-monitor-style JSON summary."""

    return json.dumps(
        {
            "run_id": "daily-fixture-run",
            "status": collection_status,
            "collection_status": collection_status,
            "analytics_status": analytics_status,
            "analytics_error_message": (
                "fixture analytics error" if analytics_status == "failed" else None
            ),
            "error_message": (
                "fixture collection error" if collection_status != "completed" else None
            ),
        }
    )
