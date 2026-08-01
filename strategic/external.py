"""Replaceable external-intelligence contracts with no-network defaults."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ExternalSourceType(StrEnum):
    """Supported external intelligence categories."""

    KBA_REGISTRATIONS = "kba_registrations"
    NEWS = "news"
    BRAND_NEWS = "brand_news"
    MARKET_DATA = "external_market_data"


class ExternalSourceStatus(StrEnum):
    """Availability state for one external source category."""

    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


class StrategicImplication(StrEnum):
    """Provider-declared strategic direction for a grounded signal."""

    OPPORTUNITY = "opportunity"
    RISK = "risk"
    CONTEXT = "context"


@dataclass(frozen=True)
class ExternalIntelligenceRequest:
    """Bounded context supplied to external intelligence providers."""

    report_date: date
    brands: tuple[str, ...]
    vehicles: tuple[str, ...]


@dataclass(frozen=True)
class ExternalSignal:
    """One source-attributed external fact or qualitative signal."""

    signal_id: str
    title: str
    summary: str
    implication: StrategicImplication
    source_url: str
    observed_at: date | datetime
    entity: str | None = None
    metric_name: str | None = None
    metric_value: int | float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class ExternalSourceSnapshot:
    """Auditable result from one optional external provider."""

    source_type: ExternalSourceType
    provider_name: str
    status: ExternalSourceStatus
    signals: tuple[ExternalSignal, ...] = ()
    limitations: tuple[str, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True)
class ExternalIntelligenceBundle:
    """All external source snapshots used by one strategic analysis."""

    kba: ExternalSourceSnapshot
    news: ExternalSourceSnapshot
    brand_news: ExternalSourceSnapshot
    market_data: ExternalSourceSnapshot

    @property
    def snapshots(self) -> tuple[ExternalSourceSnapshot, ...]:
        """Return snapshots in a stable management-report order."""

        return (self.kba, self.news, self.brand_news, self.market_data)

    @property
    def available_signal_count(self) -> int:
        """Return the number of source-attributed external signals."""

        return sum(len(snapshot.signals) for snapshot in self.snapshots)


@runtime_checkable
class KBADataProvider(Protocol):
    """Interface reserved for official KBA registration intelligence."""

    @property
    def name(self) -> str:
        """Return a stable provider identifier."""

    def fetch_registrations(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return source-attributed KBA registration signals."""


@runtime_checkable
class NewsDataProvider(Protocol):
    """Interface reserved for compliant automotive news intelligence."""

    @property
    def name(self) -> str:
        """Return a stable provider identifier."""

    def fetch_news(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return attributed news signals for the bounded request."""


@runtime_checkable
class BrandNewsDataProvider(Protocol):
    """Interface for attributed official manufacturer newsroom content."""

    @property
    def name(self) -> str:
        """Return a stable provider identifier."""

    def fetch_brand_news(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return official brand-news signals for the bounded request."""


@runtime_checkable
class ExternalMarketDataProvider(Protocol):
    """Interface reserved for third-party German market datasets."""

    @property
    def name(self) -> str:
        """Return a stable provider identifier."""

    def fetch_market_data(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        """Return attributed market signals for the bounded request."""


def collect_external_intelligence(
    request: ExternalIntelligenceRequest,
    *,
    kba_provider: KBADataProvider | None = None,
    news_provider: NewsDataProvider | None = None,
    brand_news_provider: BrandNewsDataProvider | None = None,
    market_data_provider: ExternalMarketDataProvider | None = None,
) -> ExternalIntelligenceBundle:
    """Collect optional sources independently without making default requests."""

    return ExternalIntelligenceBundle(
        kba=_collect_source(
            ExternalSourceType.KBA_REGISTRATIONS,
            None if kba_provider is None else kba_provider.name,
            (
                None
                if kba_provider is None
                else lambda: kba_provider.fetch_registrations(request)
            ),
            request.report_date,
        ),
        news=_collect_source(
            ExternalSourceType.NEWS,
            None if news_provider is None else news_provider.name,
            (
                None
                if news_provider is None
                else lambda: news_provider.fetch_news(request)
            ),
            request.report_date,
        ),
        brand_news=_collect_source(
            ExternalSourceType.BRAND_NEWS,
            None if brand_news_provider is None else brand_news_provider.name,
            (
                None
                if brand_news_provider is None
                else lambda: brand_news_provider.fetch_brand_news(request)
            ),
            request.report_date,
        ),
        market_data=_collect_source(
            ExternalSourceType.MARKET_DATA,
            None if market_data_provider is None else market_data_provider.name,
            (
                None
                if market_data_provider is None
                else lambda: market_data_provider.fetch_market_data(request)
            ),
            request.report_date,
        ),
    )


def _collect_source(
    source_type: ExternalSourceType,
    provider_name: str | None,
    fetch: Callable[[], ExternalSourceSnapshot] | None,
    report_date: date,
) -> ExternalSourceSnapshot:
    if fetch is None:
        return ExternalSourceSnapshot(
            source_type=source_type,
            provider_name="not_configured",
            status=ExternalSourceStatus.NOT_CONFIGURED,
            limitations=(
                "No provider is configured; no external facts were inferred.",
            ),
        )
    try:
        snapshot = fetch()
        _validate_snapshot(
            snapshot,
            source_type,
            provider_name or "unknown",
            report_date,
        )
        return snapshot
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "External intelligence provider failed source_type=%s provider=%s error=%s",
            source_type,
            provider_name,
            error_message,
        )
        return ExternalSourceSnapshot(
            source_type=source_type,
            provider_name=provider_name or "unknown",
            status=ExternalSourceStatus.FAILED,
            limitations=("Provider failure; its evidence was excluded from analysis.",),
            error_message=error_message,
        )


def _validate_snapshot(
    snapshot: ExternalSourceSnapshot,
    expected_type: ExternalSourceType,
    expected_provider: str,
    report_date: date,
) -> None:
    if snapshot.source_type != expected_type:
        raise ValueError(
            f"provider source type mismatch: expected={expected_type} "
            f"actual={snapshot.source_type}"
        )
    if snapshot.provider_name != expected_provider:
        raise ValueError(
            f"provider name mismatch: expected={expected_provider} "
            f"actual={snapshot.provider_name}"
        )
    if snapshot.status is not ExternalSourceStatus.AVAILABLE and snapshot.signals:
        raise ValueError("unavailable external snapshot cannot contain signals")
    for signal in snapshot.signals:
        if not signal.signal_id.strip() or not signal.title.strip():
            raise ValueError("external signal identifiers and titles must be non-empty")
        if not signal.summary.strip() or not signal.source_url.strip():
            raise ValueError("external signal summary and source URL must be non-empty")
        if not signal.source_url.startswith(("https://", "http://")):
            raise ValueError("external signal source URL must use HTTP or HTTPS")
        observed_date = (
            signal.observed_at.date()
            if isinstance(signal.observed_at, datetime)
            else signal.observed_at
        )
        if not isinstance(observed_date, date) or observed_date > report_date:
            raise ValueError(
                "external signal observation date must not exceed the report date"
            )
        if isinstance(signal.metric_value, bool):
            raise ValueError("external signal metric value cannot be boolean")
        if isinstance(signal.metric_value, float) and not math.isfinite(
            signal.metric_value
        ):
            raise ValueError("external signal metric value must be finite")
