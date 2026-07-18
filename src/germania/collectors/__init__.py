"""Collectors package for future compliant data ingestion."""

from __future__ import annotations

from germania.collectors.autoscout24 import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_COUNTRY_CODE,
    AUTOSCOUT24_DE_SOURCE_ID,
    AutoScout24Collector,
    AutoScout24ListingParser,
    ListingRecord,
    LoadedListingPage,
    PageLoader,
    PlaywrightPageLoader,
    SearchConfig,
    build_search_url,
    parse_listing,
    parse_listing_page,
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
from germania.collectors.volkswagen import (
    VOLKSWAGEN_DE_BASE_URL,
    VOLKSWAGEN_DE_COUNTRY_CODE,
    VOLKSWAGEN_DE_SOURCE_ID,
    OfficialPriceRecord,
    VolkswagenOfficialPriceImportResult,
    VolkswagenOfficialPriceImportService,
    VolkswagenOfficialPriceParser,
    parse_official_prices,
)

__all__ = [
    "AUTOSCOUT24_DE_BASE_URL",
    "AUTOSCOUT24_DE_COUNTRY_CODE",
    "AUTOSCOUT24_DE_SOURCE_ID",
    "AutoScout24Collector",
    "AutoScout24ListingParser",
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
    "ListingRecord",
    "PageLoader",
    "PlaywrightPageLoader",
    "RawCollectionMetadata",
    "RequestBudgetExceeded",
    "RetryPolicy",
    "SearchConfig",
    "VOLKSWAGEN_DE_BASE_URL",
    "VOLKSWAGEN_DE_COUNTRY_CODE",
    "VOLKSWAGEN_DE_SOURCE_ID",
    "OfficialPriceRecord",
    "VolkswagenOfficialPriceImportResult",
    "VolkswagenOfficialPriceImportService",
    "VolkswagenOfficialPriceParser",
    "build_search_url",
    "parse_official_prices",
    "parse_listing",
    "parse_listing_page",
    "run_with_retry",
]
