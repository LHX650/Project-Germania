from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from services.intelligence import (
    clear_intelligence_cache,
    load_daily_market_intelligence,
)
from services.peer_benchmarking import load_peer_benchmarks


def test_analytics_file_update_recalculates_peer_group_and_gaps(
    tmp_path: Path,
) -> None:
    database_path = _write_metadata_database(tmp_path)
    report_path = tmp_path / "daily_market_intelligence.json"
    _write_report(report_path, target_price=50_000)
    clear_intelligence_cache()

    first_report = load_daily_market_intelligence(report_path)
    first = load_peer_benchmarks(first_report, database_path).by_vehicle[
        "Dynamic Motors Alpha"
    ]

    _write_report(report_path, target_price=60_000)
    os.utime(report_path, None)
    second_report = load_daily_market_intelligence(report_path)
    second = load_peer_benchmarks(second_report, database_path).by_vehicle[
        "Dynamic Motors Alpha"
    ]

    assert first.metrics["price_gap_pct"].gap == -0.99
    assert second.metrics["price_gap_pct"].gap == 18.81
    assert second.match_level == 2


def _write_metadata_database(tmp_path: Path) -> Path:
    path = tmp_path / "metadata.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE brands (
            brand_id INTEGER PRIMARY KEY,
            canonical_brand TEXT NOT NULL,
            country_of_origin TEXT,
            active INTEGER NOT NULL
        );
        CREATE TABLE vehicles (
            vehicle_id INTEGER PRIMARY KEY,
            brand_id INTEGER NOT NULL,
            canonical_model TEXT NOT NULL,
            vehicle_segment TEXT,
            body_type TEXT,
            default_powertrain TEXT,
            active INTEGER NOT NULL
        );
        INSERT INTO brands VALUES (1, 'Dynamic Motors', 'Germany', 1);
        INSERT INTO vehicles VALUES
            (1, 1, 'Alpha', 'compact_suv', 'suv', 'battery_electric', 1),
            (2, 1, 'Beta', 'compact_suv', 'suv', 'battery_electric', 1),
            (3, 1, 'Gamma', 'compact_suv', 'suv', 'battery_electric', 1);
        """)
    connection.commit()
    connection.close()
    return path


def _write_report(path: Path, *, target_price: int) -> None:
    payload = {
        "date": "2026-08-01",
        "vehicles": [
            _vehicle("Alpha", target_price, 80),
            _vehicle("Beta", 47_000, 60),
            _vehicle("Gamma", 54_000, 70),
        ],
        "brands": [],
        "methodology": {"scope": "fixture"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _vehicle(model: str, average: int, opportunity: int) -> dict[str, object]:
    return {
        "vehicle": {"brand": "Dynamic Motors", "model": model},
        "metrics": {
            "active_listing_count": 100,
            "average_price_eur": average,
            "minimum_price_eur": average * 0.8,
            "maximum_price_eur": average * 1.2,
            "price_change_7d_pct": -2,
            "price_change_30d_pct": -1,
            "new_listings_count_7d": 20,
            "inventory_change_7d_count": 10,
            "inventory_change_7d_pct": 10,
        },
        "opportunity_score": {
            "score": opportunity,
            "components": {
                "inventory_attractiveness": 50,
                "price_competitiveness": 50,
                "price_trend": 50,
                "market_activity": 60,
            },
            "applied_weights": {
                "inventory_attractiveness": 0.3,
                "price_competitiveness": 0.3,
                "price_trend": 0.2,
                "market_activity": 0.2,
            },
        },
    }
