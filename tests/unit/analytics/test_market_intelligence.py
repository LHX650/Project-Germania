from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from germania.analytics import build_daily_market_intelligence
from germania.db import (
    Base,
    Brand,
    DataSource,
    MarketplaceListing,
    MarketplacePriceHistory,
    Vehicle,
    create_database_engine,
    create_session_factory,
    session_scope,
)

REPORT_DATE = date(2026, 7, 31)
REPORT_TIME = datetime(2026, 7, 31, 12, tzinfo=UTC)


@pytest.fixture()
def db_sessions() -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_vehicle_brand_metrics_and_opportunity_score(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, vehicles = _seed_catalog(session)
        golf_1 = _listing(
            session,
            source=source,
            vehicle=vehicles["Golf"],
            external_id="golf-1",
            fuel_type="petrol",
            price="20000",
            first_seen=REPORT_TIME - timedelta(days=40),
        )
        golf_2 = _listing(
            session,
            source=source,
            vehicle=vehicles["Golf"],
            external_id="golf-2",
            fuel_type="petrol",
            price="30000",
            first_seen=REPORT_TIME - timedelta(days=2),
        )
        model_y = _listing(
            session,
            source=source,
            vehicle=vehicles["Model Y"],
            external_id="model-y-1",
            fuel_type="electric",
            price="40000",
            first_seen=REPORT_TIME - timedelta(days=40),
        )
        _history(session, golf_1, "22000", REPORT_TIME - timedelta(days=35))
        _history(session, golf_1, "20000", REPORT_TIME - timedelta(days=1))
        _history(session, golf_2, "30000", REPORT_TIME - timedelta(days=1))
        _history(session, model_y, "42000", REPORT_TIME - timedelta(days=35))
        _history(session, model_y, "40000", REPORT_TIME - timedelta(days=1))

        report = build_daily_market_intelligence(session, report_date=REPORT_DATE)

    vehicles_by_model = {item.vehicle["model"]: item for item in report.vehicles}
    golf = vehicles_by_model["Golf"]
    assert golf.metrics.active_listing_count == 2
    assert golf.metrics.average_price_eur == Decimal("25000.00")
    assert golf.metrics.minimum_price_eur == Decimal("20000.00")
    assert golf.metrics.maximum_price_eur == Decimal("30000.00")
    assert golf.metrics.price_change_7d_pct == Decimal("13.64")
    assert golf.metrics.price_change_30d_pct == Decimal("13.64")
    assert golf.metrics.new_listings_count_7d == 1
    assert golf.metrics.inventory_change_7d_count == 1
    assert golf.metrics.inventory_change_7d_pct == Decimal("100.00")
    assert Decimal("0") <= golf.opportunity_score.score <= Decimal("100")
    assert sum(golf.opportunity_score.applied_weights.values()) == Decimal("1.00")

    brands = {item.brand: item.metrics for item in report.brands}
    assert brands["Volkswagen"].active_inventory_rank == 1
    assert brands["Volkswagen"].average_vehicle_price_eur == Decimal("25000.00")
    assert brands["Tesla"].bev_share_pct == Decimal("100.00")
    assert brands["Tesla"].phev_share_pct == Decimal("0.00")
    assert brands["Tesla"].model_coverage_pct == Decimal("100.00")
    assert "opportunity_score" in report.methodology["formulas"]


def test_empty_database_returns_empty_report(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        report = build_daily_market_intelligence(session, report_date=REPORT_DATE)

    assert report.vehicles == ()
    assert report.brands == ()
    assert report.to_dict()["vehicles"] == []
    assert report.to_dict()["brands"] == []


def test_incremental_data_changes_price_inventory_and_activity_metrics(
    db_sessions: sessionmaker[Session],
) -> None:
    with session_scope(db_sessions) as session:
        source, vehicles = _seed_catalog(session)
        original = _listing(
            session,
            source=source,
            vehicle=vehicles["Golf"],
            external_id="golf-original",
            fuel_type="petrol",
            price="18000",
            first_seen=REPORT_TIME - timedelta(days=40),
        )
        _history(session, original, "20000", REPORT_TIME - timedelta(days=10))
        _history(session, original, "18000", REPORT_TIME - timedelta(days=1))
        before = build_daily_market_intelligence(session, report_date=REPORT_DATE)

        added = _listing(
            session,
            source=source,
            vehicle=vehicles["Golf"],
            external_id="golf-added",
            fuel_type="petrol",
            price="22000",
            first_seen=REPORT_TIME - timedelta(hours=2),
        )
        _history(session, added, "22000", REPORT_TIME - timedelta(hours=2))
        after = build_daily_market_intelligence(session, report_date=REPORT_DATE)

    before_golf = before.vehicles[0].metrics
    after_golf = after.vehicles[0].metrics
    assert before_golf.active_listing_count == 1
    assert after_golf.active_listing_count == 2
    assert before_golf.average_price_eur == Decimal("18000.00")
    assert after_golf.average_price_eur == Decimal("20000.00")
    assert after_golf.new_listings_count_7d == 1
    assert after_golf.inventory_change_7d_count == 1
    assert after_golf.price_change_7d_pct == Decimal("0.00")


def _seed_catalog(session: Session) -> tuple[DataSource, dict[str, Vehicle]]:
    source = DataSource(
        source_id="analytics_test",
        source_name="Analytics test source",
        source_type="marketplace",
        country_code="DE",
        update_frequency="daily",
        authority_level="primary_commercial",
        collection_method="manual_entry",
        notes="Test only.",
    )
    volkswagen = Brand(canonical_brand="Volkswagen", active=True)
    tesla = Brand(canonical_brand="Tesla", active=True)
    session.add_all([source, volkswagen, tesla])
    session.flush()
    vehicles = {
        "Golf": Vehicle(
            brand_id=volkswagen.brand_id,
            canonical_model="Golf",
            default_powertrain="ice",
            priority_level="high",
            active=True,
        ),
        "Tiguan": Vehicle(
            brand_id=volkswagen.brand_id,
            canonical_model="Tiguan",
            default_powertrain="ice",
            priority_level="high",
            active=True,
        ),
        "Model Y": Vehicle(
            brand_id=tesla.brand_id,
            canonical_model="Model Y",
            default_powertrain="bev",
            priority_level="high",
            active=True,
        ),
    }
    session.add_all(vehicles.values())
    session.flush()
    return source, vehicles


def _listing(
    session: Session,
    *,
    source: DataSource,
    vehicle: Vehicle,
    external_id: str,
    fuel_type: str,
    price: str,
    first_seen: datetime,
) -> MarketplaceListing:
    listing = MarketplaceListing(
        data_source_id=source.data_source_id,
        external_listing_id=external_id,
        vehicle_id=vehicle.vehicle_id,
        brand_name=vehicle.brand.canonical_brand,
        model_name=vehicle.canonical_model,
        current_price_amount=Decimal(price),
        currency="EUR",
        fuel_type=fuel_type,
        first_seen_at=first_seen,
        last_seen_at=REPORT_TIME,
        last_collected_at=REPORT_TIME,
        active=True,
    )
    session.add(listing)
    session.flush()
    return listing


def _history(
    session: Session,
    listing: MarketplaceListing,
    price: str,
    observed_at: datetime,
) -> None:
    session.add(
        MarketplacePriceHistory(
            marketplace_listing_id=listing.marketplace_listing_id,
            price_amount=Decimal(price),
            currency="EUR",
            observed_at=observed_at,
            collected_at=observed_at,
        )
    )
    session.flush()
