"""Base classes and shared helpers for future collectors."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from germania.collectors.exceptions import (
    CollectorConfigurationError,
    CollectorError,
    RequestBudgetExceeded,
)
from germania.collectors.retry import RetryPolicy, run_with_retry
from germania.config.playwright import (
    PlaywrightSettings,
    load_playwright_config,
)
from germania.config.sources import load_source_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectorSource:
    """Validated source metadata used by collectors."""

    source_id: str
    source_name: str
    source_type: str
    country_code: str
    base_url: str | None
    data_categories: tuple[str, ...]
    update_frequency: str
    authority_level: str
    active: bool
    collection_method: str
    notes: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, object]) -> CollectorSource:
        """Create source metadata from validated source configuration."""
        return cls(
            source_id=str(source["source_id"]),
            source_name=str(source["source_name"]),
            source_type=str(source["source_type"]),
            country_code=str(source["country_code"]),
            base_url=(
                str(source["base_url"]) if source["base_url"] is not None else None
            ),
            data_categories=tuple(str(item) for item in source["data_categories"]),
            update_frequency=str(source["update_frequency"]),
            authority_level=str(source["authority_level"]),
            active=bool(source["active"]),
            collection_method=str(source["collection_method"]),
            notes=str(source["notes"]),
        )


@dataclass(frozen=True)
class CollectionRequest:
    """Audit record for an intended request within a collection run."""

    source_id: str
    url: str
    sequence_number: int
    requested_at: datetime
    timeout_seconds: float


@dataclass(frozen=True)
class RawCollectionMetadata:
    """Trace metadata for raw source payloads before cleaning or persistence."""

    source_id: str
    source_name: str
    source_url: str
    collected_at: datetime
    content_sha256: str | None


class BaseCollector(ABC):
    """Shared foundation for source-specific collectors.

    Subclasses should implement parsing and source-specific collection steps.
    This class owns configuration loading, request budgets, retry policy wiring,
    logging context, and raw metadata helpers.
    """

    def __init__(
        self,
        source_id: str,
        *,
        source_config_path: Path | str | None = None,
        playwright_config_path: Path | str | None = None,
        source_config: Mapping[str, object] | None = None,
        playwright_settings: PlaywrightSettings | None = None,
        environ: Mapping[str, str] | None = None,
        collector_logger: logging.Logger | None = None,
    ) -> None:
        self.source = _load_collector_source(
            source_id,
            source_config_path=source_config_path,
            source_config=source_config,
        )
        self.settings = (
            playwright_settings
            if playwright_settings is not None
            else load_playwright_config(playwright_config_path, environ=environ)
        )
        self.runtime_settings = self.settings.for_source(source_id)
        self.retry_policy = RetryPolicy.from_settings(self.runtime_settings.retry)
        self.logger = collector_logger or logging.getLogger(
            f"germania.collectors.{source_id}"
        )
        self._request_count = 0

        override = self.settings.source_overrides.get(source_id)
        if override is not None and not override.enabled:
            raise CollectorConfigurationError(
                f"Collection is disabled for source_id={source_id}"
            )
        if not self.source.active:
            raise CollectorConfigurationError(
                f"Source is inactive in configuration: source_id={source_id}"
            )

    @property
    def request_count(self) -> int:
        """Return the number of intended requests recorded in this run."""
        return self._request_count

    @property
    def request_budget(self) -> int:
        """Return the resolved max request count for this run."""
        return self.runtime_settings.max_requests_per_run

    def remaining_request_budget(self) -> int:
        """Return remaining requests before the per-run budget is exhausted."""
        return max(self.request_budget - self._request_count, 0)

    def record_request(self, url: str) -> CollectionRequest:
        """Record an intended request and enforce the configured request budget."""
        if not url.strip():
            raise CollectorError("Cannot record an empty request URL")
        if self._request_count >= self.request_budget:
            raise RequestBudgetExceeded(
                "Request budget exceeded for "
                f"source_id={self.source.source_id} "
                f"budget={self.request_budget}"
            )

        self._request_count += 1
        record = CollectionRequest(
            source_id=self.source.source_id,
            url=url,
            sequence_number=self._request_count,
            requested_at=datetime.now(UTC),
            timeout_seconds=self.runtime_settings.request_timeout_seconds,
        )
        self.logger.info(
            "Recorded collection request source_id=%s sequence=%s url=%s",
            record.source_id,
            record.sequence_number,
            record.url,
        )
        return record

    def run_with_retry(
        self,
        operation: Any,
        *,
        operation_name: str = "collector operation",
    ) -> Any:
        """Run a collector operation with this source's retry policy."""
        return run_with_retry(
            operation,
            self.retry_policy,
            operation_name=operation_name,
            operation_logger=self.logger,
        )

    def build_raw_metadata(
        self,
        source_url: str,
        raw_content: bytes | str | None = None,
    ) -> RawCollectionMetadata:
        """Build trace metadata for a raw payload without persisting it."""
        content_hash = None
        if raw_content is not None:
            payload = (
                raw_content.encode("utf-8")
                if isinstance(raw_content, str)
                else raw_content
            )
            content_hash = hashlib.sha256(payload).hexdigest()

        return RawCollectionMetadata(
            source_id=self.source.source_id,
            source_name=self.source.source_name,
            source_url=source_url,
            collected_at=datetime.now(UTC),
            content_sha256=content_hash,
        )

    @abstractmethod
    def collect(self) -> object:
        """Run the source-specific collection workflow."""


def _load_collector_source(
    source_id: str,
    *,
    source_config_path: Path | str | None,
    source_config: Mapping[str, object] | None,
) -> CollectorSource:
    config = (
        source_config
        if source_config is not None
        else load_source_config(source_config_path)
    )
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise CollectorConfigurationError("Source configuration missing sources list")

    for source in sources:
        if isinstance(source, Mapping) and source.get("source_id") == source_id:
            return CollectorSource.from_mapping(source)

    raise CollectorConfigurationError(f"Unknown source_id={source_id}")
