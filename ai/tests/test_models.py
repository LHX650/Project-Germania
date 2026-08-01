"""Tests for strict Phase 5A Analytics JSON parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.models import AnalyticsInputError, load_analytics_input, parse_analytics_input


def analytics_payload() -> dict[str, object]:
    """Return a minimal valid Analytics payload with real-schema fields."""

    return {
        "date": "2026-07-31",
        "vehicles": [
            {
                "vehicle": {"brand": "Example", "model": "Model One"},
                "metrics": {
                    "active_listing_count": 10,
                    "average_price_eur": 42_000.0,
                    "minimum_price_eur": 39_000.0,
                    "maximum_price_eur": 48_000.0,
                    "price_change_7d_pct": -1.25,
                    "price_change_30d_pct": None,
                    "new_listings_count_7d": 3,
                    "inventory_change_7d_count": 2,
                    "inventory_change_7d_pct": 25.0,
                },
                "opportunity_score": {
                    "score": 73.5,
                    "components": {
                        "inventory_attractiveness": 80.0,
                        "price_competitiveness": 70.0,
                        "price_trend": None,
                        "market_activity": 65.0,
                    },
                    "applied_weights": {
                        "inventory_attractiveness": 0.35,
                        "price_competitiveness": 0.30,
                        "market_activity": 0.35,
                    },
                },
            }
        ],
        "brands": [
            {
                "brand": "Example",
                "metrics": {
                    "active_inventory_count": 10,
                    "active_inventory_rank": 1,
                    "average_vehicle_price_eur": 42_000.0,
                    "bev_share_pct": 70.0,
                    "phev_share_pct": 20.0,
                    "bev_phev_share_pct": 90.0,
                    "model_coverage_count": 1,
                    "catalog_model_count": 2,
                    "model_coverage_pct": 50.0,
                },
            }
        ],
        "methodology": {"source": "test fixture"},
    }


def write_payload(path: Path, payload: object | None = None) -> Path:
    """Write a UTF-8 JSON fixture and return its path."""

    path.write_text(
        json.dumps(analytics_payload() if payload is None else payload),
        encoding="utf-8",
    )
    return path


def test_load_analytics_input_parses_real_schema(tmp_path: Path) -> None:
    report = load_analytics_input(write_payload(tmp_path / "daily.json"))

    assert report.report_date.isoformat() == "2026-07-31"
    assert report.active_inventory_count == 10
    assert report.new_listings_count_7d == 3
    assert report.inventory_change_7d_count == 2
    assert report.weighted_average_price_eur == 42_000.0
    assert report.vehicles[0].opportunity_score.score == 73.5


@pytest.mark.parametrize(
    ("field", "value"),
    (("date", "31-07-2026"), ("vehicles", {}), ("brands", None)),
)
def test_parse_analytics_input_rejects_invalid_root_fields(
    field: str,
    value: object,
) -> None:
    payload = analytics_payload()
    payload[field] = value

    with pytest.raises(AnalyticsInputError):
        parse_analytics_input(payload)


def test_load_analytics_input_rejects_invalid_json(tmp_path: Path) -> None:
    source = tmp_path / "broken.json"
    source.write_text("{", encoding="utf-8")

    with pytest.raises(AnalyticsInputError, match="valid UTF-8 JSON"):
        load_analytics_input(source)
