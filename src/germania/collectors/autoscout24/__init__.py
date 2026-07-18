"""German AutoScout24 collector foundation."""

from __future__ import annotations

from germania.collectors.autoscout24.collector import (
    AutoScout24Collector,
    LoadedListingPage,
)
from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_COUNTRY_CODE,
    AUTOSCOUT24_DE_SOURCE_ID,
    DEFAULT_SORT,
    SearchConfig,
)
from germania.collectors.autoscout24.loader import PageLoader, PlaywrightPageLoader
from germania.collectors.autoscout24.models import ListingRecord
from germania.collectors.autoscout24.parser import (
    AutoScout24ListingParser,
    parse_listing,
    parse_listing_page,
)
from germania.collectors.autoscout24.urls import build_search_url

__all__ = [
    "AUTOSCOUT24_DE_BASE_URL",
    "AUTOSCOUT24_DE_COUNTRY_CODE",
    "AUTOSCOUT24_DE_SOURCE_ID",
    "DEFAULT_SORT",
    "AutoScout24Collector",
    "AutoScout24ListingParser",
    "LoadedListingPage",
    "ListingRecord",
    "PageLoader",
    "PlaywrightPageLoader",
    "SearchConfig",
    "build_search_url",
    "parse_listing",
    "parse_listing_page",
]
