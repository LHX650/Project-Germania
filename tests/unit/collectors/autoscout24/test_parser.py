from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from germania.collectors.autoscout24 import (
    AutoScout24ListingParser,
    ListingRecord,
    parse_listing,
    parse_listing_page,
    parse_marketplace_listing_page,
)
from germania.collectors.marketplace import MarketplaceListingRecord

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "autoscout24"
COLLECTED_AT = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)


def test_parse_single_listing_fixture() -> None:
    record = parse_listing(
        _fixture_text("single_listing.html"), collected_at=COLLECTED_AT
    )

    assert isinstance(record, ListingRecord)
    assert record.source_id == "autoscout24_de"
    assert record.listing_id == "as24-golf-001"
    assert record.brand == "Volkswagen"
    assert record.model == "Golf"
    assert record.variant == "1.5 eTSI Life DSG"
    assert record.price == Decimal("24990")
    assert record.currency == "EUR"
    assert record.registration == "03/2021"
    assert record.mileage == 42000
    assert record.fuel_type == "Benzin"
    assert record.transmission == "Automatik"
    assert record.power == "110 kW (150 PS)"
    assert record.location == "DE-10115 Berlin"
    assert record.url == (
        "https://www.autoscout24.de/angebote/" "volkswagen-golf-life-dsg-as24-golf-001"
    )
    assert record.collected_at == COLLECTED_AT


def test_parse_listing_page_fixture_with_multiple_listings() -> None:
    records = parse_listing_page(
        _fixture_text("listing_page.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 2
    assert [record.listing_id for record in records] == [
        "as24-golf-001",
        "as24-id4-002",
    ]
    assert [record.model for record in records] == ["Golf", "ID.4"]
    assert [record.price for record in records] == [Decimal("24990"), Decimal("31500")]
    assert all(record.collected_at == COLLECTED_AT for record in records)


def test_parse_empty_listing_page_returns_empty_list() -> None:
    records = AutoScout24ListingParser().parse_listing_page(
        _fixture_text("empty_page.html"),
        collected_at=COLLECTED_AT,
    )

    assert records == []


def test_parse_listing_with_missing_fields_keeps_none_values() -> None:
    records = parse_listing_page(
        _fixture_text("missing_fields.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    record = records[0]
    assert record.listing_id == "as24-missing-003"
    assert record.brand == "Volkswagen"
    assert record.model == "Golf"
    assert record.variant is None
    assert record.price is None
    assert record.currency is None
    assert record.registration is None
    assert record.mileage is None
    assert record.fuel_type is None
    assert record.transmission is None
    assert record.power is None
    assert record.location is None


def test_parse_malformed_listing_html_does_not_crash() -> None:
    records = parse_listing_page(
        _fixture_text("malformed_listing.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 1
    record = records[0]
    assert record.listing_id == "as24-broken-004"
    assert record.brand is not None
    assert record.price == Decimal("19990")


def test_parse_non_listing_fragment_returns_none() -> None:
    record = parse_listing("<html><body>No listing card here</body></html>")

    assert record is None


def test_parse_marketplace_fixture_normalizes_repository_fields() -> None:
    records = parse_marketplace_listing_page(
        _fixture_text("fixture_pipeline.html"),
        collected_at=COLLECTED_AT,
    )

    assert len(records) == 6
    record = records[0]
    assert isinstance(record, MarketplaceListingRecord)
    assert record.external_listing_id == "as24-golf-101"
    assert record.price_amount == Decimal("24990")
    assert record.registration_year == 2021
    assert record.mileage_km == 42000
    assert record.power_kw == Decimal("110")
    assert record.listing_url == (
        "https://www.autoscout24.de/angebote/" "volkswagen-golf-life-as24-golf-101"
    )
    assert record.fuel_type == "petrol"
    assert record.transmission == "automatic"
    assert record.seller_type == "dealer"
    assert record.seller_postcode == "10115"
    assert record.seller_city == "Berlin"
    assert record.vehicle_condition == "used"


def test_marketplace_parser_ignores_non_vehicle_prices_and_keeps_optional_nulls() -> (
    None
):
    records = parse_marketplace_listing_page(
        _fixture_text("fixture_pipeline.html"),
        collected_at=COLLECTED_AT,
    )

    optional_record = records[1]
    assert optional_record.external_listing_id == "as24-golf-102"
    assert optional_record.price_amount == Decimal("18750.00")
    assert optional_record.registration_year is None
    assert optional_record.mileage_km is None
    assert optional_record.power_kw is None
    assert optional_record.variant_name is None

    no_sale_price_record = records[3]
    assert no_sale_price_record.external_listing_id == "as24-golf-no-price"
    assert no_sale_price_record.price_amount is None


def _fixture_text(filename: str) -> str:
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")
