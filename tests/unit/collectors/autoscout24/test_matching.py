from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from germania.collectors.autoscout24.matching import (
    evaluate_vehicle_matches,
    match_listing_record,
)
from germania.collectors.marketplace import MarketplaceListingRecord

SEAL_U_INCLUDE_KEYWORDS = ("Seal U", "Sealion 6", "Seal U DM-i")
SEAL_U_EXCLUDE_KEYWORDS = (
    "Seal 6",
    "Seal Sedan",
    "Seal Performance",
    "SEALION 7",
)


@pytest.mark.parametrize(
    ("title", "model_name"),
    [
        ("BYD Seal U Design", "Seal U"),
        ("BYD Seal SEAL U-DM-i Boost", "Seal"),
        ("BYD Sealion 6 Comfort", "Seal"),
    ],
)
def test_seal_u_positive_keywords_accept_supported_names(
    title: str,
    model_name: str,
) -> None:
    decision = match_listing_record(
        _record(title, model_name),
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
        exclude_keywords=SEAL_U_EXCLUDE_KEYWORDS,
    )

    assert decision.status == "matched"
    assert decision.reason.startswith("included_keyword:")


@pytest.mark.parametrize(
    ("title", "model_name", "expected_reason"),
    [
        ("BYD Seal Comfort", "Seal", "conflicting_canonical_model:Seal"),
        ("BYD Seal Performance", "Seal", "excluded_keyword:Seal Performance"),
        ("BYD Seal 6 DM-i", "Seal", "excluded_keyword:Seal 6"),
        ("BYD SEALION 7 Excellence", "Seal", "excluded_keyword:SEALION 7"),
    ],
)
def test_seal_u_rejects_conflicting_or_excluded_models(
    title: str,
    model_name: str,
    expected_reason: str,
) -> None:
    decision = match_listing_record(
        _record(title, model_name),
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
        exclude_keywords=SEAL_U_EXCLUDE_KEYWORDS,
    )

    assert decision.status == "rejected"
    assert decision.reason == expected_reason


def test_exclusion_takes_precedence_over_positive_keyword() -> None:
    decision = match_listing_record(
        _record("BYD Seal U Seal 6 DM-i", "Seal U"),
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
        exclude_keywords=SEAL_U_EXCLUDE_KEYWORDS,
    )

    assert decision.status == "rejected"
    assert decision.reason == "excluded_keyword:Seal 6"


def test_known_canonical_model_preserves_existing_task_compatibility() -> None:
    decision = match_listing_record(
        _record("Mercedes-Benz GLC 220 d 4Matic", "GLC 220"),
        expected_model_name="GLC",
    )

    assert decision.status == "matched"
    assert decision.reason == "canonical_model_match"


def test_unknown_model_without_positive_match_is_low_confidence() -> None:
    decision = match_listing_record(
        _record("BYD electric SUV", "Unknown edition"),
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
    )

    assert decision.status == "low_confidence"
    assert decision.reason == "unknown_model_without_include_match"


def test_keyword_match_does_not_span_title_and_model_fields() -> None:
    decision = match_listing_record(
        _record("BYD Seal", "U"),
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
    )

    assert decision.status == "low_confidence"


def test_non_matched_records_are_made_non_importable_and_reasons_are_counted() -> None:
    evaluation = evaluate_vehicle_matches(
        [
            _record("BYD Seal U Design", "Seal", listing_id="matched"),
            _record("BYD Seal Comfort", "Seal", listing_id="rejected"),
            _record("BYD electric SUV", "Unknown edition", listing_id="low"),
        ],
        expected_model_name="Seal U",
        include_keywords=SEAL_U_INCLUDE_KEYWORDS,
        exclude_keywords=SEAL_U_EXCLUDE_KEYWORDS,
    )

    assert evaluation.summary.matched == 1
    assert evaluation.summary.rejected == 1
    assert evaluation.summary.low_confidence == 1
    assert evaluation.summary.total == 3
    assert evaluation.records[0].model_name == "Seal U"
    assert evaluation.records[1].model_name is None
    assert evaluation.records[2].model_name is None
    assert evaluation.summary.reason_counts == {
        "conflicting_canonical_model:Seal": 1,
        "included_keyword:Seal U": 1,
        "unknown_model_without_include_match": 1,
    }


def _record(
    title: str,
    model_name: str,
    *,
    listing_id: str = "listing-1",
) -> MarketplaceListingRecord:
    return MarketplaceListingRecord(
        source_id="autoscout24_de",
        external_listing_id=listing_id,
        collected_at=datetime(2026, 7, 31, tzinfo=UTC),
        listing_url=f"https://www.autoscout24.de/angebote/{listing_id}",
        brand_name="BYD",
        model_name=model_name,
        title=title,
        price_amount=Decimal("39990"),
    )
