"""Collectors package for future compliant data ingestion."""

from __future__ import annotations

from germania.collectors.autoscout24 import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_COUNTRY_CODE,
    AUTOSCOUT24_DE_SOURCE_ID,
    AutoScout24Collector,
    LoadedListingPage,
    PageLoader,
    PlaywrightPageLoader,
    SearchConfig,
    build_search_url,
)
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
    "AUTOSCOUT24_DE_BASE_URL",
    "AUTOSCOUT24_DE_COUNTRY_CODE",
    "AUTOSCOUT24_DE_SOURCE_ID",
    "AutoScout24Collector",
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
    "LoadedListingPage",
    "PageLoader",
    "PlaywrightPageLoader",
    "RawCollectionMetadata",
    "RequestBudgetExceeded",
    "RetryPolicy",
    "SearchConfig",
    "build_search_url",
    "run_with_retry",
]
