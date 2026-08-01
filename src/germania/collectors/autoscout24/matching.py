"""Configuration-driven vehicle matching for AutoScout24 listings."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Literal

from germania.collectors.marketplace import MarketplaceListingRecord
from germania.config import UNKNOWN, normalize_model

logger = logging.getLogger(__name__)

VehicleMatchStatus = Literal["matched", "rejected", "low_confidence"]
_NON_WORD_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True)
class VehicleMatchDecision:
    """Explain whether one listing belongs to the configured vehicle."""

    status: VehicleMatchStatus
    reason: str
    matched_keyword: str | None = None


@dataclass(frozen=True)
class VehicleMatchSummary:
    """Aggregate matching outcomes for one page, task, or collection run."""

    matched: int = 0
    rejected: int = 0
    low_confidence: int = 0
    reason_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Return the total number of evaluated listing records."""

        return self.matched + self.rejected + self.low_confidence


@dataclass(frozen=True)
class VehicleMatchEvaluation:
    """Records prepared for import plus their aggregate matching summary."""

    records: tuple[MarketplaceListingRecord, ...]
    summary: VehicleMatchSummary


def match_listing_record(
    record: MarketplaceListingRecord,
    *,
    expected_model_name: str | None,
    include_keywords: tuple[str, ...] = (),
    exclude_keywords: tuple[str, ...] = (),
) -> VehicleMatchDecision:
    """Return an explainable matching decision for one parsed listing.

    Exclusions take precedence. A positive keyword match is accepted next,
    followed by an exact canonical-model fallback for existing vehicle tasks.
    A known conflicting model is rejected; an unknown model without a positive
    keyword is treated as low confidence.
    """

    searchable_texts = _searchable_texts(record)
    excluded_keyword = _first_matching_keyword(searchable_texts, exclude_keywords)
    if excluded_keyword is not None:
        return VehicleMatchDecision(
            status="rejected",
            reason=f"excluded_keyword:{excluded_keyword}",
            matched_keyword=excluded_keyword,
        )

    included_keyword = _first_matching_keyword(searchable_texts, include_keywords)
    if included_keyword is not None:
        return VehicleMatchDecision(
            status="matched",
            reason=f"included_keyword:{included_keyword}",
            matched_keyword=included_keyword,
        )

    if expected_model_name is None:
        if include_keywords:
            return VehicleMatchDecision(
                status="low_confidence",
                reason="no_include_keyword_match",
            )
        return VehicleMatchDecision(
            status="matched",
            reason="matching_not_configured",
        )

    expected_model = normalize_model(expected_model_name)
    observed_model = normalize_model(record.model_name)
    if expected_model != UNKNOWN and observed_model == expected_model:
        return VehicleMatchDecision(
            status="matched",
            reason="canonical_model_match",
        )
    if observed_model != UNKNOWN:
        return VehicleMatchDecision(
            status="rejected",
            reason=f"conflicting_canonical_model:{observed_model}",
        )
    return VehicleMatchDecision(
        status="low_confidence",
        reason="unknown_model_without_include_match",
    )


def evaluate_vehicle_matches(
    records: Iterable[MarketplaceListingRecord],
    *,
    expected_model_name: str | None,
    include_keywords: tuple[str, ...] = (),
    exclude_keywords: tuple[str, ...] = (),
    match_logger: logging.Logger | None = None,
) -> VehicleMatchEvaluation:
    """Evaluate records and make rejected or low-confidence rows non-importable."""

    output: list[MarketplaceListingRecord] = []
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    active_logger = match_logger or logger

    for record in records:
        decision = match_listing_record(
            record,
            expected_model_name=expected_model_name,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
        )
        statuses[decision.status] += 1
        reasons[decision.reason] += 1
        if decision.status == "matched":
            output.append(
                replace(record, model_name=expected_model_name)
                if expected_model_name is not None
                else record
            )
            continue

        output.append(replace(record, model_name=None))
        active_logger.warning(
            "AutoScout24 vehicle match status=%s reason=%s listing_id=%s "
            "expected_model=%s observed_model=%s title=%s",
            decision.status,
            decision.reason,
            record.external_listing_id,
            expected_model_name,
            record.model_name,
            record.title,
        )

    return VehicleMatchEvaluation(
        records=tuple(output),
        summary=VehicleMatchSummary(
            matched=statuses["matched"],
            rejected=statuses["rejected"],
            low_confidence=statuses["low_confidence"],
            reason_counts=dict(sorted(reasons.items())),
        ),
    )


def combine_match_summaries(
    summaries: Iterable[VehicleMatchSummary],
) -> VehicleMatchSummary:
    """Combine page or task matching summaries."""

    matched = 0
    rejected = 0
    low_confidence = 0
    reasons: Counter[str] = Counter()
    for summary in summaries:
        matched += summary.matched
        rejected += summary.rejected
        low_confidence += summary.low_confidence
        reasons.update(summary.reason_counts)
    return VehicleMatchSummary(
        matched=matched,
        rejected=rejected,
        low_confidence=low_confidence,
        reason_counts=dict(sorted(reasons.items())),
    )


def _searchable_texts(record: MarketplaceListingRecord) -> tuple[str, ...]:
    values = (record.title, record.model_name)
    return tuple(_normalize_match_text(value) for value in values if value)


def _first_matching_keyword(
    searchable_texts: tuple[str, ...],
    keywords: tuple[str, ...],
) -> str | None:
    for keyword in keywords:
        normalized_keyword = _normalize_match_text(keyword)
        if normalized_keyword and any(
            f" {normalized_keyword} " in f" {searchable_text} "
            for searchable_text in searchable_texts
        ):
            return keyword
    return None


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(_NON_WORD_PATTERN.sub(" ", normalized).split())
