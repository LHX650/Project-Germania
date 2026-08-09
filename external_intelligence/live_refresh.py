"""Non-blocking stale-while-revalidate coordination for live intelligence."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai.intelligence.models import ExternalEvidence
from ai.intelligence.providers import ExternalQuery
from external_intelligence.live_providers import (
    LiveExternalCollection,
    LiveProviderResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderRefreshStatus:
    """One provider category's most recent bounded refresh outcome."""

    provider_kind: str
    status: str
    successful_sources: tuple[str, ...]
    failed_sources: tuple[str, ...]
    insufficient_sources: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class LiveRefreshState:
    """Last valid content plus non-blocking refresh diagnostics."""

    collection: LiveExternalCollection | None
    provider_statuses: tuple[ProviderRefreshStatus, ...]
    last_attempt_at: datetime | None
    error_message: str | None
    refreshing: bool = False


class LiveCollectionSnapshotStore:
    """Persist the last valid collection without replacing it on failure."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)

    def load(self) -> LiveRefreshState:
        """Load a validated snapshot; corrupt or absent cache is treated as empty."""

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                return _empty_state()
            collection = _collection_from_dict(payload.get("collection"))
            attempt = payload.get("last_attempt")
            if not isinstance(attempt, dict):
                attempt = {}
            statuses = _statuses_from_list(attempt.get("providers"))
            attempted_at = _datetime_or_none(attempt.get("completed_at"))
            error = attempt.get("error_message")
            return LiveRefreshState(
                collection=collection,
                provider_statuses=statuses,
                last_attempt_at=attempted_at,
                error_message=str(error).strip() if error else None,
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return _empty_state()

    def record_collection(
        self,
        collection: LiveExternalCollection,
        *,
        completed_at: datetime,
    ) -> None:
        """Record an attempt and replace content only when evidence is valid."""

        previous = self.load()
        preserved = _preserve_failed_provider_evidence(
            collection,
            previous.collection,
        )
        errors = tuple(
            error for provider in collection.providers for error in provider.errors
        )
        self._write(
            collection=preserved,
            statuses=_provider_statuses(collection.providers),
            completed_at=completed_at,
            error_message="; ".join(errors) or None,
        )

    def record_error(self, error: str, *, completed_at: datetime) -> None:
        """Record a failed refresh while retaining the previous valid content."""

        previous = self.load()
        self._write(
            collection=previous.collection,
            statuses=previous.provider_statuses,
            completed_at=completed_at,
            error_message=error,
        )

    def _write(
        self,
        *,
        collection: LiveExternalCollection | None,
        statuses: tuple[ProviderRefreshStatus, ...],
        completed_at: datetime,
        error_message: str | None,
    ) -> None:
        payload = {
            "version": 1,
            "collection": (
                _collection_to_dict(collection) if collection is not None else None
            ),
            "last_attempt": {
                "completed_at": completed_at.astimezone(UTC).isoformat(),
                "providers": [asdict(item) for item in statuses],
                "error_message": error_message,
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class LiveRefreshCoordinator:
    """Allow one background refresh per cache cycle across Streamlit reruns."""

    def __init__(
        self,
        *,
        loader: Callable[[ExternalQuery], LiveExternalCollection],
        store: LiveCollectionSnapshotStore,
        refresh_interval_seconds: float = 900.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be positive")
        self.loader = loader
        self.store = store
        self.refresh_interval = timedelta(seconds=refresh_interval_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._refreshing = False

    def state(self) -> LiveRefreshState:
        """Return cached content immediately with current in-process activity."""

        stored = self.store.load()
        with self._lock:
            refreshing = self._refreshing
        return LiveRefreshState(
            collection=stored.collection,
            provider_statuses=stored.provider_statuses,
            last_attempt_at=stored.last_attempt_at,
            error_message=stored.error_message,
            refreshing=refreshing,
        )

    def request_refresh(self, query: ExternalQuery, *, force: bool = False) -> bool:
        """Start one daemon refresh unless running or inside the cooldown window."""

        now = self._clock().astimezone(UTC)
        with self._lock:
            if self._refreshing:
                return False
            last_attempt = self.store.load().last_attempt_at
            if (
                not force
                and last_attempt is not None
                and now - last_attempt.astimezone(UTC) < self.refresh_interval
            ):
                return False
            self._refreshing = True
        thread = threading.Thread(
            target=self._run,
            args=(query,),
            name="global-intelligence-refresh",
            daemon=True,
        )
        thread.start()
        return True

    def _run(self, query: ExternalQuery) -> None:
        try:
            collection = self.loader(query)
            self.store.record_collection(
                collection,
                completed_at=self._clock().astimezone(UTC),
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            logger.warning("Live intelligence background refresh failed: %s", message)
            try:
                self.store.record_error(
                    message,
                    completed_at=self._clock().astimezone(UTC),
                )
            except Exception as cache_exc:
                logger.warning(
                    "Live intelligence refresh status cache failed: %s: %s",
                    type(cache_exc).__name__,
                    cache_exc,
                )
        finally:
            with self._lock:
                self._refreshing = False


def _collection_to_dict(collection: LiveExternalCollection) -> dict[str, Any]:
    return {
        "fetched_at": collection.fetched_at.astimezone(UTC).isoformat(),
        "evidence": [asdict(item) for item in collection.evidence],
        "providers": [
            {
                **asdict(item),
                "evidence": [asdict(evidence) for evidence in item.evidence],
            }
            for item in collection.providers
        ],
    }


def _preserve_failed_provider_evidence(
    current: LiveExternalCollection,
    previous: LiveExternalCollection | None,
) -> LiveExternalCollection | None:
    """Keep previous evidence only for provider sources that failed this attempt."""

    if previous is None:
        return current if current.evidence else None
    if not current.evidence:
        return previous
    previous_by_kind = {item.provider_kind: item for item in previous.providers}
    merged_providers: list[LiveProviderResult] = []
    merged_evidence: list[ExternalEvidence] = list(current.evidence)
    current_kinds: set[str] = set()
    for provider in current.providers:
        current_kinds.add(provider.provider_kind)
        previous_provider = previous_by_kind.get(provider.provider_kind)
        fallback: tuple[ExternalEvidence, ...] = ()
        if previous_provider is not None:
            if provider.status == "failed":
                fallback = previous_provider.evidence
            elif provider.failed_sources:
                failed_sources = set(provider.failed_sources)
                fallback = tuple(
                    item
                    for item in previous_provider.evidence
                    if item.source in failed_sources
                )
        provider_evidence = _deduplicate_evidence((*provider.evidence, *fallback))
        merged_evidence.extend(fallback)
        merged_providers.append(replace(provider, evidence=provider_evidence))
    for provider in previous.providers:
        if provider.provider_kind in current_kinds:
            continue
        merged_providers.append(provider)
        merged_evidence.extend(provider.evidence)
    return LiveExternalCollection(
        fetched_at=current.fetched_at,
        evidence=_deduplicate_evidence(tuple(merged_evidence)),
        providers=tuple(merged_providers),
    )


def _deduplicate_evidence(
    items: tuple[ExternalEvidence, ...],
) -> tuple[ExternalEvidence, ...]:
    by_url: dict[str, ExternalEvidence] = {}
    for item in items:
        by_url.setdefault(item.url, item)
    return tuple(by_url.values())


def _collection_from_dict(value: object) -> LiveExternalCollection | None:
    if not isinstance(value, dict):
        return None
    fetched_at = _datetime_or_none(value.get("fetched_at"))
    raw_evidence = value.get("evidence")
    raw_providers = value.get("providers")
    if fetched_at is None or not isinstance(raw_evidence, list):
        return None
    evidence = tuple(
        ExternalEvidence(**item) for item in raw_evidence if isinstance(item, dict)
    )
    providers: list[LiveProviderResult] = []
    if isinstance(raw_providers, list):
        for item in raw_providers:
            if not isinstance(item, dict):
                continue
            provider_evidence = tuple(
                ExternalEvidence(**entry)
                for entry in item.get("evidence", [])
                if isinstance(entry, dict)
            )
            providers.append(
                LiveProviderResult(
                    provider_name=str(item["provider_name"]),
                    provider_kind=str(item["provider_kind"]),
                    status=str(item["status"]),
                    evidence=provider_evidence,
                    successful_sources=tuple(item.get("successful_sources", ())),
                    failed_sources=tuple(item.get("failed_sources", ())),
                    insufficient_sources=tuple(item.get("insufficient_sources", ())),
                    errors=tuple(item.get("errors", ())),
                )
            )
    return LiveExternalCollection(
        fetched_at=fetched_at,
        evidence=evidence,
        providers=tuple(providers),
    )


def _provider_statuses(
    providers: tuple[LiveProviderResult, ...],
) -> tuple[ProviderRefreshStatus, ...]:
    return tuple(
        ProviderRefreshStatus(
            provider_kind=item.provider_kind,
            status=item.status,
            successful_sources=item.successful_sources,
            failed_sources=item.failed_sources,
            insufficient_sources=item.insufficient_sources,
            errors=item.errors,
        )
        for item in providers
    )


def _statuses_from_list(value: object) -> tuple[ProviderRefreshStatus, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        ProviderRefreshStatus(
            provider_kind=str(item.get("provider_kind", "")),
            status=str(item.get("status", "failed")),
            successful_sources=tuple(item.get("successful_sources", ())),
            failed_sources=tuple(item.get("failed_sources", ())),
            insufficient_sources=tuple(item.get("insufficient_sources", ())),
            errors=tuple(item.get("errors", ())),
        )
        for item in value
        if isinstance(item, dict) and item.get("provider_kind")
    )


def _datetime_or_none(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cached refresh timestamps must include a time zone")
    return parsed.astimezone(UTC)


def _empty_state() -> LiveRefreshState:
    return LiveRefreshState(
        collection=None,
        provider_statuses=(),
        last_attempt_at=None,
        error_message=None,
    )
