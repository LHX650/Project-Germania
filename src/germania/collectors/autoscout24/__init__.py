"""German AutoScout24 collector foundation."""

from __future__ import annotations

from germania.collectors.autoscout24.batch import (
    AutoScout24BatchCollectionPipeline,
    AutoScout24BatchCollectionResult,
    AutoScout24BatchPageResult,
    BatchCollectionMode,
)
from germania.collectors.autoscout24.collector import (
    AutoScout24Collector,
    ListingPageLoadFailure,
    LoadedListingPage,
)
from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_BASE_URL,
    AUTOSCOUT24_DE_COUNTRY_CODE,
    AUTOSCOUT24_DE_SOURCE_ID,
    DEFAULT_SORT,
    SearchConfig,
)
from germania.collectors.autoscout24.import_service import (
    AutoScout24ImportResult,
    AutoScout24ListingImportService,
    combine_import_results,
)
from germania.collectors.autoscout24.loader import (
    PageLoader,
    PageLoadResult,
    PlaywrightPageLoader,
)
from germania.collectors.autoscout24.models import ListingRecord
from germania.collectors.autoscout24.parser import (
    AutoScout24ListingParser,
    parse_listing,
    parse_listing_page,
    parse_marketplace_listing_page,
)
from germania.collectors.autoscout24.single_page import (
    AutoScout24SinglePagePipeline,
    AutoScout24SinglePageResult,
    SinglePageMode,
)
from germania.collectors.autoscout24.urls import build_search_url

__all__ = [
    "AUTOSCOUT24_DE_BASE_URL",
    "AUTOSCOUT24_DE_COUNTRY_CODE",
    "AUTOSCOUT24_DE_SOURCE_ID",
    "DEFAULT_SORT",
    "AutoScout24Collector",
    "AutoScout24BatchCollectionPipeline",
    "AutoScout24BatchCollectionResult",
    "AutoScout24BatchPageResult",
    "AutoScout24ImportResult",
    "AutoScout24ListingImportService",
    "AutoScout24ListingParser",
    "AutoScout24SinglePagePipeline",
    "AutoScout24SinglePageResult",
    "BatchCollectionMode",
    "ListingPageLoadFailure",
    "LoadedListingPage",
    "ListingRecord",
    "PageLoader",
    "PageLoadResult",
    "PlaywrightPageLoader",
    "SearchConfig",
    "SinglePageMode",
    "build_search_url",
    "combine_import_results",
    "parse_listing",
    "parse_listing_page",
    "parse_marketplace_listing_page",
]
