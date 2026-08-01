from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from germania.collectors.autoscout24 import AutoScout24ListingImportService
from germania.collectors.autoscout24.batch import _apply_title_exclusions
from germania.collectors.autoscout24.matching import evaluate_vehicle_matches
from germania.collectors.marketplace import MarketplaceListingRecord
from germania.db import (
    Base,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from germania.db.seed import seed_configuration


def test_configured_title_exclusion_is_counted_as_rejected() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    collected_at = datetime(2026, 7, 19, 9, tzinfo=UTC)
    records = [
        _record("seal-1", "BYD Seal Excellence", collected_at),
        _record("seal-u-1", "BYD Seal U DM-i Boost", collected_at),
    ]

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            filtered = _apply_title_exclusions(records, ("Seal U", "Seal 6"))
            result = AutoScout24ListingImportService(session).import_records(filtered)

            assert result.total == 2
            assert result.inserted == 1
            assert result.rejected == 1
            assert result.price_history_inserted == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_rejected_and_low_confidence_records_do_not_enter_database() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    collected_at = datetime(2026, 7, 31, 9, tzinfo=UTC)
    records = [
        _record("seal-u-1", "BYD Seal U DM-i Boost", collected_at),
        _record("seal-1", "BYD Seal Comfort", collected_at),
        _record(
            "unknown-1",
            "BYD electric SUV",
            collected_at,
            model_name="Unknown edition",
        ),
    ]

    try:
        with session_scope(session_factory) as session:
            seed_configuration(session)
            evaluation = evaluate_vehicle_matches(
                records,
                expected_model_name="Seal U",
                include_keywords=("Seal U", "Sealion 6", "Seal U DM-i"),
                exclude_keywords=("Seal 6", "Seal Performance", "SEALION 7"),
            )
            result = AutoScout24ListingImportService(session).import_records(
                evaluation.records
            )

            assert evaluation.summary.matched == 1
            assert evaluation.summary.rejected == 1
            assert evaluation.summary.low_confidence == 1
            assert result.total == 3
            assert result.inserted == 1
            assert result.rejected == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _record(
    listing_id: str,
    title: str,
    collected_at: datetime,
    *,
    model_name: str = "Seal",
) -> MarketplaceListingRecord:
    return MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id=listing_id,
        collected_at=collected_at,
        listing_url=f"https://www.autoscout24.de/angebote/{listing_id}",
        brand_name="BYD",
        model_name=model_name,
        title=title,
        price_amount=Decimal("39990"),
    )
