"""Collectors package for future compliant data ingestion."""

from __future__ import annotations

from germania.collectors.base import (
    BaseCollector,
    CollectionRequest,
    CollectorSource,
    RawCollectionMetadata,
)
from germania.collectors.browser import BrowserManager
from germania.collectors.exceptions import (
    CollectorAccessDeniedError,
    CollectorConfigurationError,
    CollectorDependencyError,
    CollectorError,
    CollectorTimeoutError,
    CollectorTransientError,
    RequestBudgetExceeded,
)
from germania.collectors.retry import RetryPolicy, run_with_retry

__all__ = [
    "BaseCollector",
    "BrowserManager",
    "CollectionRequest",
    "CollectorAccessDeniedError",
    "CollectorConfigurationError",
    "CollectorDependencyError",
    "CollectorError",
    "CollectorSource",
    "CollectorTimeoutError",
    "CollectorTransientError",
    "RawCollectionMetadata",
    "RequestBudgetExceeded",
    "RetryPolicy",
    "run_with_retry",
]
