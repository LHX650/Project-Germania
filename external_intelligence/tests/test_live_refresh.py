"""Tests for non-blocking live-intelligence refresh isolation."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import ExternalQuery
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveProviderResult,
    collect_live_external_intelligence,
)
from external_intelligence.live_refresh import (
    LiveCollectionSnapshotStore,
    LiveRefreshCoordinator,
)

NOW = datetime(2026, 8, 9, 6, tzinfo=UTC)


def test_collection_returns_completed_provider_when_another_times_out() -> None:
    started = time.monotonic()

    collection = collect_live_external_intelligence(
        (_ImmediateProvider(), _BlockingProvider(0.25)),
        ExternalQuery(query=""),
        fetched_at=NOW,
        provider_timeout_seconds=0.03,
    )

    elapsed = time.monotonic() - started
    assert elapsed < 0.15
    assert [item.title for item in collection.evidence] == ["Verified update"]
    statuses = {item.provider_kind: item for item in collection.providers}
    assert statuses["automotive_news"].status == "available"
    assert statuses["official_brand_news"].status == "failed"
    assert "bounded collection timeout" in statuses["official_brand_news"].errors[0]


def test_failed_refresh_preserves_last_valid_collection(tmp_path: Path) -> None:
    store = LiveCollectionSnapshotStore(tmp_path / "latest_collection.json")
    valid = _collection(_available_result())
    failed = _collection(_failed_result(), evidence=())
    store.record_collection(valid, completed_at=NOW)

    store.record_collection(failed, completed_at=NOW)

    state = store.load()
    assert state.collection is not None
    assert [item.title for item in state.collection.evidence] == ["Verified update"]
    assert state.provider_statuses[0].status == "failed"
    assert state.provider_statuses[0].failed_sources == ("Unavailable source",)


def test_partial_refresh_preserves_only_failed_source_evidence(tmp_path: Path) -> None:
    store = LiveCollectionSnapshotStore(tmp_path / "latest_collection.json")
    tesla = _evidence_for("Tesla Blog", "https://example.org/tesla")
    previous_provider = LiveProviderResult(
        provider_name="brands",
        provider_kind="official_brand_news",
        status="available",
        evidence=(tesla,),
        successful_sources=("Tesla Blog",),
        failed_sources=(),
    )
    store.record_collection(
        _collection(previous_provider),
        completed_at=NOW,
    )
    bmw = _evidence_for("BMW PressClub", "https://example.org/bmw")
    partial_provider = LiveProviderResult(
        provider_name="brands",
        provider_kind="official_brand_news",
        status="partial",
        evidence=(bmw,),
        successful_sources=("BMW PressClub",),
        failed_sources=("Tesla Blog",),
        errors=("Tesla Blog: HTTP 403",),
    )

    store.record_collection(
        _collection(partial_provider),
        completed_at=NOW,
    )

    state = store.load()
    assert state.collection is not None
    assert {item.source for item in state.collection.evidence} == {
        "BMW PressClub",
        "Tesla Blog",
    }
    assert {item.source for item in state.collection.providers[0].evidence} == {
        "BMW PressClub",
        "Tesla Blog",
    }


def test_reruns_share_one_refresh_and_respect_failure_cooldown(
    tmp_path: Path,
) -> None:
    release = threading.Event()
    started = threading.Event()
    calls = 0

    def loader(query: ExternalQuery) -> LiveExternalCollection:
        nonlocal calls
        del query
        calls += 1
        started.set()
        release.wait(timeout=1)
        return _collection(_failed_result(), evidence=())

    coordinator = LiveRefreshCoordinator(
        loader=loader,
        store=LiveCollectionSnapshotStore(tmp_path / "latest_collection.json"),
        refresh_interval_seconds=900,
        clock=lambda: NOW,
    )
    query = ExternalQuery(query="")

    assert coordinator.request_refresh(query) is True
    assert started.wait(timeout=1)
    assert coordinator.request_refresh(query) is False
    assert coordinator.request_refresh(query, force=True) is False
    release.set()
    _wait_until_complete(coordinator)

    assert calls == 1
    assert coordinator.request_refresh(query) is False


def _wait_until_complete(coordinator: LiveRefreshCoordinator) -> None:
    deadline = time.monotonic() + 1
    while coordinator.state().refreshing and time.monotonic() < deadline:
        time.sleep(0.005)
    assert coordinator.state().refreshing is False


def _evidence() -> ExternalEvidence:
    return _evidence_for("Official source", "https://example.org/update")


def _evidence_for(source: str, url: str) -> ExternalEvidence:
    return ExternalEvidence(
        source=source,
        title="Verified update",
        url=url,
        published_date="2026-08-08T08:00:00+00:00",
        category="automotive_news",
        brand=None,
        vehicle=None,
        content_summary="Verified metadata.",
        reliability=95,
        fetched_time=NOW.isoformat(),
        evidence_type="official_industry_news",
        region="EU",
    )


def _available_result() -> LiveProviderResult:
    evidence = _evidence()
    return LiveProviderResult(
        provider_name="available",
        provider_kind="automotive_news",
        status="available",
        evidence=(evidence,),
        successful_sources=("Official source",),
        failed_sources=(),
    )


def _failed_result() -> LiveProviderResult:
    return LiveProviderResult(
        provider_name="failed",
        provider_kind="official_brand_news",
        status="failed",
        evidence=(),
        successful_sources=(),
        failed_sources=("Unavailable source",),
        errors=("HTTP 403",),
    )


def _collection(
    provider: LiveProviderResult,
    *,
    evidence: tuple[ExternalEvidence, ...] | None = None,
) -> LiveExternalCollection:
    return LiveExternalCollection(
        fetched_at=NOW,
        evidence=provider.evidence if evidence is None else evidence,
        providers=(provider,),
    )


class _ImmediateProvider:
    name = "immediate"
    provider_kind = "automotive_news"
    sources = ()
    max_items = 5

    def fetch(self, query: ExternalQuery) -> LiveProviderResult:
        del query
        return _available_result()


class _BlockingProvider:
    name = "blocking"
    provider_kind = "official_brand_news"
    sources = ()
    max_items = 5

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def fetch(self, query: ExternalQuery) -> LiveProviderResult:
        del query
        time.sleep(self.delay)
        return _failed_result()
