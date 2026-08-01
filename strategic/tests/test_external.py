"""Tests for optional external intelligence provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from strategic.external import (
    ExternalIntelligenceRequest,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
    collect_external_intelligence,
)


@dataclass(frozen=True)
class StubKBAProvider:
    """Source-attributed local test implementation of the KBA interface."""

    name: str = "fixture-kba"

    def fetch_registrations(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        return ExternalSourceSnapshot(
            source_type=ExternalSourceType.KBA_REGISTRATIONS,
            provider_name=self.name,
            status=ExternalSourceStatus.AVAILABLE,
            signals=(
                ExternalSignal(
                    signal_id="kba-fixture-1",
                    title="Fixture registration signal",
                    summary=f"Fixture evidence for {request.report_date.isoformat()}.",
                    implication=StrategicImplication.CONTEXT,
                    source_url="https://example.test/kba-fixture",
                    observed_at=request.report_date,
                    metric_name="new_registrations",
                    metric_value=100,
                    unit="vehicles",
                ),
            ),
        )


@dataclass(frozen=True)
class FailingNewsProvider:
    """Test implementation representing an unavailable news API."""

    name: str = "fixture-news"

    def fetch_news(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        del request
        raise TimeoutError("fixture timeout")


def test_no_provider_performs_no_external_collection() -> None:
    bundle = collect_external_intelligence(_request())

    assert bundle.available_signal_count == 0
    assert all(
        snapshot.status is ExternalSourceStatus.NOT_CONFIGURED
        for snapshot in bundle.snapshots
    )
    assert all(snapshot.signals == () for snapshot in bundle.snapshots)


def test_configured_provider_returns_attributed_signal() -> None:
    bundle = collect_external_intelligence(
        _request(),
        kba_provider=StubKBAProvider(),
    )

    assert bundle.kba.status is ExternalSourceStatus.AVAILABLE
    assert bundle.kba.signals[0].metric_value == 100
    assert bundle.news.status is ExternalSourceStatus.NOT_CONFIGURED
    assert bundle.available_signal_count == 1


def test_provider_failure_is_isolated_as_status() -> None:
    bundle = collect_external_intelligence(
        _request(),
        news_provider=FailingNewsProvider(),
    )

    assert bundle.news.status is ExternalSourceStatus.FAILED
    assert "fixture timeout" in (bundle.news.error_message or "")
    assert bundle.news.signals == ()
    assert bundle.kba.status is ExternalSourceStatus.NOT_CONFIGURED


def _request() -> ExternalIntelligenceRequest:
    return ExternalIntelligenceRequest(
        report_date=date(2026, 7, 31),
        brands=("Dynamic Motors",),
        vehicles=("Dynamic Motors Alpha",),
    )
