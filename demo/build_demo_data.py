"""Build the public synthetic Project Germania Dashboard demo bundle."""

# ruff: noqa: E402 -- the standalone builder adds src/ before package imports.

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import create_engine, insert

from germania.db import Base

DEMO_DIR = Path(__file__).resolve().parent
DEMO_DATABASE = DEMO_DIR / "project_germania_demo.sqlite3"
REPORT_DATE = date(2026, 7, 31)
GENERATED_AT = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
RUN_ID = "demo-run-20260731-public"
PIPELINE_ID = "demo-pipeline-20260731-public"
REPOSITORY_URL = (
    "https://github.com/LHX650/Project-Germania/" "tree/develop-v2-intelligence/demo"
)


@dataclass(frozen=True)
class DemoVehicle:
    """One public vehicle label with synthetic market values."""

    brand: str
    model: str
    country: str
    segment: str
    powertrain: str
    inventory: int
    average_price: int
    price_change_7d: float
    price_change_30d: float
    new_listings: int
    inventory_change: int
    opportunity_score: float
    components: dict[str, float]


DEMO_VEHICLES: tuple[DemoVehicle, ...] = (
    DemoVehicle(
        "Volkswagen",
        "ID.4",
        "Germany",
        "midsize_electric_suv",
        "battery_electric",
        14,
        44_500,
        -1.8,
        -3.2,
        5,
        2,
        76.0,
        {
            "inventory_attractiveness": 78.0,
            "price_competitiveness": 72.0,
            "price_trend": 66.0,
            "market_activity": 90.0,
        },
    ),
    DemoVehicle(
        "Tesla",
        "Model Y",
        "United States",
        "midsize_electric_suv",
        "battery_electric",
        13,
        43_000,
        -2.4,
        -4.5,
        6,
        3,
        82.0,
        {
            "inventory_attractiveness": 75.0,
            "price_competitiveness": 84.0,
            "price_trend": 73.0,
            "market_activity": 98.0,
        },
    ),
    DemoVehicle(
        "BMW",
        "iX1",
        "Germany",
        "compact_electric_suv",
        "battery_electric",
        10,
        48_500,
        -0.6,
        -1.4,
        3,
        1,
        68.0,
        {
            "inventory_attractiveness": 58.0,
            "price_competitiveness": 60.0,
            "price_trend": 57.0,
            "market_activity": 75.0,
        },
    ),
    DemoVehicle(
        "Audi",
        "Q4 e-tron",
        "Germany",
        "midsize_electric_suv",
        "battery_electric",
        9,
        50_500,
        -1.1,
        -2.0,
        3,
        1,
        71.0,
        {
            "inventory_attractiveness": 54.0,
            "price_competitiveness": 52.0,
            "price_trend": 61.0,
            "market_activity": 80.0,
        },
    ),
    DemoVehicle(
        "BYD",
        "Seal U",
        "China",
        "midsize_suv",
        "plug_in_hybrid",
        8,
        39_500,
        0.5,
        1.2,
        2,
        2,
        64.0,
        {
            "inventory_attractiveness": 48.0,
            "price_competitiveness": 92.0,
            "price_trend": 45.0,
            "market_activity": 62.0,
        },
    ),
    DemoVehicle(
        "Mercedes-Benz",
        "EQA",
        "Germany",
        "compact_electric_suv",
        "battery_electric",
        10,
        49_500,
        -0.9,
        -2.5,
        4,
        2,
        70.0,
        {
            "inventory_attractiveness": 58.0,
            "price_competitiveness": 56.0,
            "price_trend": 63.0,
            "market_activity": 84.0,
        },
    ),
)


def main() -> None:
    """Generate every public demo artifact inside the isolated demo directory."""

    _assert_demo_target(DEMO_DATABASE)
    analytics = _analytics_payload()
    analytics_text = _json_text(analytics)
    _build_database()
    analytics_path = DEMO_DIR / "daily_market_intelligence.json"
    analytics_path.write_text(
        analytics_text,
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(analytics_path.read_bytes()).hexdigest()
    (DEMO_DIR / "daily_ai_market_report.md").write_text(
        _ai_report(evidence_sha256),
        encoding="utf-8",
    )
    (DEMO_DIR / "external_intelligence.json").write_text(
        _json_text(_external_intelligence_payload()),
        encoding="utf-8",
    )
    (DEMO_DIR / "content_feed.json").write_text(
        _json_text(_content_feed_payload()),
        encoding="utf-8",
    )
    (DEMO_DIR / "strategic_market_report.md").write_text(
        _strategic_report(),
        encoding="utf-8",
    )
    (DEMO_DIR / "pipeline_status.json").write_text(
        _json_text(_pipeline_status_payload()),
        encoding="utf-8",
    )


def _build_database() -> None:
    if DEMO_DATABASE.exists():
        DEMO_DATABASE.unlink()
    engine = create_engine(f"sqlite:///{DEMO_DATABASE.as_posix()}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _insert_demo_database_rows(connection)
    engine.dispose()


def _insert_demo_database_rows(connection: Any) -> None:
    created_at = GENERATED_AT
    connection.execute(
        insert(Base.metadata.tables["data_sources"]),
        [
            {
                "data_source_id": 1,
                "source_id": "project_germania_public_demo",
                "source_name": "Project Germania Demo Marketplace",
                "source_type": "marketplace",
                "country_code": "DE",
                "base_url": REPOSITORY_URL,
                "update_frequency": "manual",
                "authority_level": "primary_commercial",
                "active": True,
                "collection_method": "manual_entry",
                "notes": _json_compact(
                    {
                        "classification": "synthetic_anonymized_demo",
                        "production_data": False,
                    }
                ),
                "created_at": created_at,
                "updated_at": created_at,
            }
        ],
    )
    connection.execute(
        insert(Base.metadata.tables["brands"]),
        [
            {
                "brand_id": index,
                "canonical_brand": vehicle.brand,
                "country_of_origin": vehicle.country,
                "active": True,
                "created_at": created_at,
                "updated_at": created_at,
            }
            for index, vehicle in enumerate(DEMO_VEHICLES, start=1)
        ],
    )
    connection.execute(
        insert(Base.metadata.tables["vehicles"]),
        [
            {
                "vehicle_id": index,
                "brand_id": index,
                "canonical_model": vehicle.model,
                "vehicle_segment": vehicle.segment,
                "body_type": "suv",
                "default_powertrain": vehicle.powertrain,
                "priority_level": "high",
                "active": True,
                "created_at": created_at,
                "updated_at": created_at,
            }
            for index, vehicle in enumerate(DEMO_VEHICLES, start=1)
        ],
    )

    batches = []
    listings = []
    observations = []
    price_history = []
    listing_id = 1
    observation_id = 1
    price_history_id = 1
    for vehicle_id, vehicle in enumerate(DEMO_VEHICLES, start=1):
        batches.append(
            {
                "collection_batch_id": vehicle_id,
                "data_source_id": 1,
                "batch_id": f"demo-batch-{vehicle_id:02d}",
                "record_type": "marketplace_listing",
                "collection_method": "manual_entry",
                "collection_job_id": RUN_ID,
                "started_at": GENERATED_AT - timedelta(minutes=12 - vehicle_id),
                "completed_at": GENERATED_AT - timedelta(minutes=6 - vehicle_id),
                "status": "completed",
                "record_count": vehicle.inventory,
                "success_count": vehicle.inventory,
                "failure_count": 0,
                "source_file_name": "synthetic_demo_fixture",
                "parser_version": "demo-v2.0",
                "notes": _json_compact(
                    {
                        "requested_pages": 1,
                        "succeeded_pages": 1,
                        "matched": vehicle.inventory,
                        "rejected": 0,
                        "low_confidence": 0,
                        "import_rejected": 0,
                        "demo_dataset": True,
                    }
                ),
                "created_at": created_at,
            }
        )
        prices = _vehicle_prices(vehicle)
        for item_index, price in enumerate(prices, start=1):
            external_id = (
                f"DEMO-{_slug(vehicle.brand)}-{_slug(vehicle.model)}-{item_index:03d}"
            )
            first_seen = GENERATED_AT - timedelta(days=(item_index % 6), hours=2)
            listing_url = f"{REPOSITORY_URL}#demo-listing-{listing_id:03d}"
            listings.append(
                {
                    "marketplace_listing_id": listing_id,
                    "data_source_id": 1,
                    "external_listing_id": external_id,
                    "vehicle_id": vehicle_id,
                    "brand_name": vehicle.brand,
                    "model_name": vehicle.model,
                    "variant_name": "Public Demo Edition",
                    "title": (
                        f"{vehicle.brand} {vehicle.model} — synthetic demo listing"
                    ),
                    "current_price_amount": price,
                    "currency": "EUR",
                    "registration_year": 2024 + (item_index % 2),
                    "model_year": str(2024 + (item_index % 2)),
                    "fuel_type": vehicle.powertrain,
                    "transmission": "automatic",
                    "power_kw": 150 + item_index,
                    "vehicle_condition": "used",
                    "body_type": "suv",
                    "color": "Demo neutral",
                    "mileage_km": 4_000 + item_index * 1_650,
                    "owner_count": 1,
                    "seller_type": "dealer",
                    "seller_name": f"Demo Dealer {vehicle_id:02d}",
                    "country_code": "DE",
                    "state": "Demo Region",
                    "seller_city": "Demo City",
                    "seller_postcode": f"D{vehicle_id:02d}{item_index:03d}",
                    "listing_url": listing_url,
                    "first_seen_at": first_seen,
                    "last_seen_at": GENERATED_AT,
                    "last_collected_at": GENERATED_AT,
                    "source_updated_at": GENERATED_AT,
                    "active": True,
                    "notes": _json_compact(
                        {
                            "demo_dataset": True,
                            "synthetic": True,
                            "production_record": False,
                        }
                    ),
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )
            for days_before, multiplier in ((13, 1.025), (6, 1.012), (0, 1.0)):
                observed_at = GENERATED_AT - timedelta(days=days_before)
                observed_price = int(round(price * multiplier))
                observations.append(
                    {
                        "marketplace_listing_observation_id": observation_id,
                        "marketplace_listing_id": listing_id,
                        "collection_batch_id": vehicle_id,
                        "listed_price": observed_price,
                        "currency": "EUR",
                        "price_includes_vat": True,
                        "observed_at": observed_at,
                        "collected_at": observed_at,
                        "listing_status": "active",
                        "mileage_km": 4_000 + item_index * 1_650,
                        "source_url": listing_url,
                        "data_quality_status": "valid",
                        "validation_status": "passed",
                        "duplicate_key": f"{external_id}:{observed_at.date()}",
                        "notes": _json_compact({"demo_dataset": True}),
                        "created_at": created_at,
                    }
                )
                observation_id += 1
            for days_before, multiplier in ((13, 1.025), (0, 1.0)):
                observed_at = GENERATED_AT - timedelta(days=days_before)
                price_history.append(
                    {
                        "marketplace_price_history_id": price_history_id,
                        "marketplace_listing_id": listing_id,
                        "price_amount": int(round(price * multiplier)),
                        "currency": "EUR",
                        "observed_at": observed_at,
                        "collected_at": observed_at,
                        "source_updated_at": observed_at,
                        "listing_url": listing_url,
                        "notes": _json_compact({"demo_dataset": True}),
                        "created_at": created_at,
                    }
                )
                price_history_id += 1
            listing_id += 1

    connection.execute(insert(Base.metadata.tables["collection_batches"]), batches)
    connection.execute(insert(Base.metadata.tables["marketplace_listings"]), listings)
    connection.execute(
        insert(Base.metadata.tables["marketplace_listing_observations"]),
        observations,
    )
    connection.execute(
        insert(Base.metadata.tables["marketplace_price_history"]),
        price_history,
    )
    connection.execute(
        insert(Base.metadata.tables["data_quality_issues"]),
        [
            {
                "data_quality_issue_id": 1,
                "entity_type": "demo_bundle",
                "entity_id": "public-v2",
                "issue_code": "SYNTHETIC_DEMO_NOTICE",
                "severity": "informational",
                "description": (
                    "All database records are synthetic and intended only for "
                    "public Dashboard demonstrations."
                ),
                "resolution_status": "accepted",
                "detected_at": created_at,
                "resolution_notes": "Expected condition for DEMO_MODE=true.",
                "created_at": created_at,
                "updated_at": created_at,
            }
        ],
    )


def _analytics_payload() -> dict[str, Any]:
    weights = {
        "inventory_attractiveness": 0.3,
        "price_competitiveness": 0.3,
        "price_trend": 0.2,
        "market_activity": 0.2,
    }
    vehicles = []
    for vehicle in DEMO_VEHICLES:
        prices = _vehicle_prices(vehicle)
        previous_inventory = vehicle.inventory - vehicle.inventory_change
        vehicles.append(
            {
                "vehicle": {"brand": vehicle.brand, "model": vehicle.model},
                "metrics": {
                    "active_listing_count": vehicle.inventory,
                    "average_price_eur": float(vehicle.average_price),
                    "minimum_price_eur": float(min(prices)),
                    "maximum_price_eur": float(max(prices)),
                    "price_change_7d_pct": vehicle.price_change_7d,
                    "price_change_30d_pct": vehicle.price_change_30d,
                    "new_listings_count_7d": vehicle.new_listings,
                    "inventory_change_7d_count": vehicle.inventory_change,
                    "inventory_change_7d_pct": round(
                        vehicle.inventory_change / previous_inventory * 100,
                        2,
                    ),
                },
                "opportunity_score": {
                    "score": vehicle.opportunity_score,
                    "components": vehicle.components,
                    "applied_weights": weights,
                },
            }
        )
    ranked = sorted(DEMO_VEHICLES, key=lambda item: -item.inventory)
    brands = [
        {
            "brand": vehicle.brand,
            "metrics": {
                "active_inventory_count": vehicle.inventory,
                "active_inventory_rank": ranked.index(vehicle) + 1,
                "average_vehicle_price_eur": float(vehicle.average_price),
                "bev_share_pct": (
                    100.0 if vehicle.powertrain == "battery_electric" else 0.0
                ),
                "phev_share_pct": (
                    100.0 if vehicle.powertrain == "plug_in_hybrid" else 0.0
                ),
                "bev_phev_share_pct": 100.0,
                "model_coverage_count": 1,
                "catalog_model_count": 1,
                "model_coverage_pct": 100.0,
            },
        }
        for vehicle in DEMO_VEHICLES
    ]
    return {
        "date": REPORT_DATE.isoformat(),
        "vehicles": vehicles,
        "brands": brands,
        "methodology": {
            "data_classification": "synthetic_anonymized_public_demo",
            "production_data": False,
            "scope": (
                "Synthetic marketplace asking prices and listing inventory for "
                "UI demonstration only; listing counts are not sales and asking "
                "prices are not transaction prices."
            ),
            "opportunity_score_weights": weights,
            "missing_data_rules": {
                "prices": "Return null; never impute missing prices.",
                "historical_baseline": (
                    "Return null when a valid historical baseline is unavailable."
                ),
                "catalog": ("Return null coverage when a brand has no catalog models."),
                "empty_database": "Return empty vehicles and brands arrays.",
            },
        },
    }


def _content_items() -> list[dict[str, Any]]:
    collected_at = "2026-07-31T11:45:00+00:00"
    return [
        {
            "content_id": "demo-news-audi-q4",
            "content_type": "news",
            "title": "Audi Q4 e-tron public source example",
            "source_name": "Audi MediaCenter",
            "source_url": (
                "https://www.audi.com/en/press-releases/"
                "the-right-car-for-any-situation-the-audi-q4-e-tron-"
                "takes-to-the-streets-18015"
            ),
            "published_at": "2026-06-25T00:00:00+00:00",
            "summary": (
                "Short demo metadata links an official Audi Q4 e-tron article "
                "to the synthetic vehicle intelligence record."
            ),
            "language": "en",
            "region": "DE",
            "brands": ["Audi"],
            "vehicles": ["Audi Q4 e-tron"],
            "topics": ["electric mobility", "official news"],
            "impact_level": "medium",
            "thumbnail_url": None,
            "document_url": None,
            "video_id": None,
            "collected_at": collected_at,
            "evidence_status": "verified_public_example",
            "ai_summary": (
                "Demo association: official model communication can be reviewed "
                "beside synthetic price and inventory indicators."
            ),
            "summary_mode": "demo_curated",
        },
        {
            "content_id": "demo-report-acea-roads-2026",
            "content_type": "report",
            "title": "Report – Vehicles on European roads 2026",
            "source_name": "European Automobile Manufacturers' Association (ACEA)",
            "source_url": (
                "https://www.acea.auto/publication/"
                "report-vehicles-on-european-roads-2026/"
            ),
            "published_at": "2026-01-15T09:00:00+00:00",
            "summary": (
                "Official ACEA report-page metadata is included to demonstrate "
                "report cards and outbound document links."
            ),
            "language": "en",
            "region": "EU",
            "brands": [],
            "vehicles": [],
            "topics": ["vehicle fleet", "European market", "official report"],
            "impact_level": "high",
            "thumbnail_url": None,
            "document_url": (
                "https://www.acea.auto/files/"
                "ACEA_Report-%E2%80%93-Vehicles_on_European_roads_2026.pdf"
            ),
            "video_id": None,
            "collected_at": collected_at,
            "evidence_status": "verified_public_example",
            "ai_summary": (
                "Demo context: European fleet structure provides macro-level "
                "background but does not replace KBA model registrations."
            ),
            "summary_mode": "demo_curated",
        },
        {
            "content_id": "demo-video-bmw-design",
            "content_type": "video",
            "title": (
                "From the Original to the Original – 25 Years of MINI Design "
                "at the BMW Group"
            ),
            "source_name": "BMW Group",
            "source_url": "https://www.youtube.com/watch?v=sdEpKjyata8",
            "published_at": "2026-07-28T08:05:30+00:00",
            "summary": (
                "Official public YouTube metadata is included to verify video "
                "cards and embedded playback in the demo."
            ),
            "language": "en",
            "region": "GLOBAL",
            "brands": ["BMW"],
            "vehicles": [],
            "topics": ["design", "brand history", "official video"],
            "impact_level": "low",
            "thumbnail_url": None,
            "document_url": None,
            "video_id": "sdEpKjyata8",
            "collected_at": collected_at,
            "evidence_status": "verified_public_example",
            "ai_summary": (
                "Demo context: brand-history content is evidence metadata, not a "
                "quantitative market signal."
            ),
            "summary_mode": "demo_curated",
        },
    ]


def _content_feed_payload() -> dict[str, Any]:
    items = _content_items()
    sources = [
        {
            "source_id": "demo_audi_official",
            "source_name": "Audi MediaCenter",
            "source_url": "https://www.audi.com/en/press-releases/",
            "status": "demo_snapshot",
            "cache_status": "bundled",
            "record_count": 1,
            "updated_at": "2026-07-31T11:45:00+00:00",
            "limitation": "Bundled public metadata; no live request in Demo Mode.",
        },
        {
            "source_id": "demo_acea_report",
            "source_name": "ACEA",
            "source_url": "https://www.acea.auto/publications/",
            "status": "demo_snapshot",
            "cache_status": "bundled",
            "record_count": 1,
            "updated_at": "2026-07-31T11:45:00+00:00",
            "limitation": "Bundled public metadata; no live request in Demo Mode.",
        },
        {
            "source_id": "demo_bmw_youtube",
            "source_name": "BMW Group",
            "source_url": "https://www.youtube.com/@BMWGroup",
            "status": "demo_snapshot",
            "cache_status": "bundled",
            "record_count": 1,
            "updated_at": "2026-07-31T11:45:00+00:00",
            "limitation": "Bundled public metadata; no live request in Demo Mode.",
        },
    ]
    return {
        "schema_version": "1.0",
        "report_date": REPORT_DATE.isoformat(),
        "generated_at": GENERATED_AT.isoformat(),
        "counts": {kind: 1 for kind in ("news", "report", "video")},
        "items": items,
        "sources": sources,
        "data_classification": "public_demo_with_synthetic_market_data",
    }


def _external_intelligence_payload() -> dict[str, Any]:
    items = _content_items()
    news_item = items[0]
    return {
        "schema_version": "1.0",
        "report_date": REPORT_DATE.isoformat(),
        "generated_at": GENERATED_AT.isoformat(),
        "data_classification": "public_demo_metadata",
        "kba": {
            "status": "not_included_in_demo",
            "provider": "kba_official_interface",
            "records": [],
            "limitations": [
                "The public demo does not bundle or simulate KBA registrations."
            ],
        },
        "news": {
            "status": "demo_snapshot",
            "provider": "public_official_metadata",
            "articles": [],
            "limitations": ["No live network request is made in Demo Mode."],
        },
        "brand_news": {
            "status": "demo_snapshot",
            "provider": "official_brand_metadata",
            "articles": [
                {
                    "article_id": news_item["content_id"],
                    "title": news_item["title"],
                    "summary": news_item["summary"],
                    "url": news_item["source_url"],
                    "source": news_item["source_name"],
                    "source_url": "https://www.audi.com/en/press-releases/",
                    "published_at": news_item["published_at"],
                    "brands": news_item["brands"],
                    "models": news_item["vehicles"],
                    "country": news_item["region"],
                    "tags": news_item["topics"],
                    "official_brand_news": True,
                }
            ],
            "limitations": ["Short metadata only; no article body is bundled."],
        },
        "sources": _content_feed_payload()["sources"],
    }


def _pipeline_status_payload() -> dict[str, Any]:
    stages = (
        "collection",
        "analytics",
        "ai",
        "external_intelligence",
        "content_feed",
        "strategic",
    )
    return {
        "pipeline_id": PIPELINE_ID,
        "pipeline_status": "completed_demo",
        "run_id": RUN_ID,
        **{f"{stage}_status": "demo_fixture" for stage in stages},
        "timestamps": {
            "demo_bundle_generated_at": GENERATED_AT.isoformat(),
        },
        "report_paths": {
            "analytics": "demo/daily_market_intelligence.json",
            "ai": "demo/daily_ai_market_report.md",
            "external_intelligence": "demo/external_intelligence.json",
            "content_feed": "demo/content_feed.json",
            "strategic": "demo/strategic_market_report.md",
            "pipeline_status": "demo/pipeline_status.json",
        },
        "errors": {},
        "data_classification": "synthetic_anonymized_public_demo",
    }


def _ai_report(evidence_sha256: str) -> str:
    return f"""# Project Germania V2.0 — Demo German Automotive Market Report

> **Public demo:** Every quantitative market value below is synthetic and
> anonymized. It is included only to demonstrate the reporting interface.

**Generation mode:** `demo_local_rules`
**LLM provider:** `none`
**Analytics evidence SHA-256:** `{evidence_sha256}`

**Analytics date:** {REPORT_DATE.isoformat()}

## Germany market overview

The synthetic demo contains **64 active listings** across six configured vehicle
labels. These are demonstration inventory records, not sales or registrations.
The weighted asking-price level is shown only to exercise the Dashboard metrics.

## Brand competition analysis

Volkswagen and Tesla have the largest synthetic demo inventories. Every brand
has one covered model, so coverage percentages are illustrative rather than a
claim about the real German market.

## Vehicle opportunity analysis

Tesla Model Y has the highest synthetic Opportunity Score in this bundle, while
Volkswagen ID.4 provides the largest demo inventory. The values demonstrate
ranking and peer-comparison behavior only.

## Price trend interpretation

Most synthetic electric-SUV records use modest negative asking-price trends so
the Price Pressure views contain meaningful variation. BYD Seal U uses a small
positive trend to demonstrate the opposite direction.

## Inventory change interpretation

Synthetic inventory grows across the six vehicle records. This is listing
activity, not vehicle sales, deliveries, or confirmed demand.

## Risk and opportunity summary

- **Opportunity:** The bundled data demonstrates how price, inventory, activity,
  Opportunity Score, and peer benchmarks are presented together.
- **Risk:** Demo values must never be used for commercial decisions or described
  as current German market evidence.
- **Data boundary:** KBA registrations are intentionally absent and are not
  simulated.
"""


def _strategic_report() -> str:
    return """# Project Germania V2.0 — Demo Strategic Market Report

> **Public demo:** This document uses synthetic market metrics and a small set of
> public official content links. It is not a production recommendation.

**Generation mode:** `demo_local_rules`
**Report date:** 2026-07-31

## Market Opportunity

The demo highlights how peer-controlled price positioning and listing activity
can be combined into a transparent opportunity view.

## Competitive Risk

The principal demonstration risk is confusing synthetic asking-price and
inventory values with transaction prices, registrations, deliveries, or sales.

## Strategic Recommendation

Use the public bundle to review platform behavior. Run the governed production
Pipeline and validate source evidence before making any market decision.

## Evidence Boundary

- Synthetic database and Analytics metrics: `demo/`
- Public official content metadata: Audi MediaCenter, ACEA, and BMW Group
- KBA registrations: not included and not simulated
"""


def _vehicle_prices(vehicle: DemoVehicle) -> list[int]:
    midpoint = (vehicle.inventory - 1) / 2
    return [
        int(round(vehicle.average_price + (index - midpoint) * 750))
        for index in range(vehicle.inventory)
    ]


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _json_compact(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _assert_demo_target(path: Path) -> None:
    resolved_demo = DEMO_DIR.resolve(strict=True)
    resolved_target = path.resolve(strict=False)
    if resolved_target.parent != resolved_demo or resolved_target.name != (
        "project_germania_demo.sqlite3"
    ):
        raise RuntimeError(f"Refusing to write outside the demo directory: {path}")


if __name__ == "__main__":
    main()
