"""AutoScout24 Germany collector foundation."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType

from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_SOURCE_ID,
    SearchConfig,
)
from germania.collectors.autoscout24.loader import (
    PageLoader,
    PageLoadResult,
    PlaywrightPageLoader,
)
from germania.collectors.autoscout24.urls import build_search_url
from germania.collectors.base import BaseCollector, RawCollectionMetadata
from germania.collectors.browser import BrowserManager
from germania.collectors.exceptions import CollectorConfigurationError
from germania.config.playwright import PlaywrightSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedListingPage:
    """Raw loaded listing page plus trace metadata."""

    search_config: SearchConfig
    url: str
    html: str
    metadata: RawCollectionMetadata


@dataclass(frozen=True)
class ListingPageLoadFailure:
    """Failure details for one AutoScout24 listing page load."""

    search_config: SearchConfig
    url: str
    error_message: str


class AutoScout24Collector(BaseCollector):
    """Foundation collector for German AutoScout24 listing pages."""

    def __init__(
        self,
        *,
        source_config_path: Path | str | None = None,
        playwright_config_path: Path | str | None = None,
        source_config: Mapping[str, object] | None = None,
        playwright_settings: PlaywrightSettings | None = None,
        environ: Mapping[str, str] | None = None,
        page_loader: PageLoader | None = None,
        browser_manager: BrowserManager | None = None,
        collector_logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            AUTOSCOUT24_DE_SOURCE_ID,
            source_config_path=source_config_path,
            playwright_config_path=playwright_config_path,
            source_config=source_config,
            playwright_settings=playwright_settings,
            environ=environ,
            collector_logger=collector_logger,
        )
        _validate_german_autoscout24_source(self.source.base_url)
        if page_loader is None:
            self._browser_manager = browser_manager or BrowserManager(self.settings)
            self._page_loader = PlaywrightPageLoader(self._browser_manager)
        else:
            self._browser_manager = browser_manager
            self._page_loader = page_loader

    def __enter__(self) -> AutoScout24Collector:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the browser manager used by this collector, if present."""
        loader_close = getattr(self._page_loader, "close", None)
        try:
            if loader_close is not None:
                loader_close()
        finally:
            if self._browser_manager is not None:
                self._browser_manager.close()

    def build_search_url(self, search_config: SearchConfig) -> str:
        """Build a German AutoScout24 search URL for the provided configuration."""
        assert self.source.base_url is not None
        return build_search_url(search_config, base_url=self.source.base_url)

    def load_listing_page(self, search_config: SearchConfig) -> LoadedListingPage:
        """Load a listing page and return raw HTML without parsing it."""
        url = self.build_search_url(search_config)
        self.record_request(url)
        html = self.run_with_retry(
            lambda: self._page_loader.load_listing_page(
                url,
                timeout_seconds=self.runtime_settings.request_timeout_seconds,
            ),
            operation_name="autoscout24 listing page load",
        )

        return LoadedListingPage(
            search_config=search_config,
            url=url,
            html=html,
            metadata=self.build_raw_metadata(url, html),
        )

    def load_listing_pages(
        self,
        search_config: SearchConfig,
        *,
        max_pages: int = 3,
    ) -> list[LoadedListingPage | ListingPageLoadFailure]:
        """Load consecutive listing pages without parsing them."""
        if max_pages <= 0:
            raise ValueError("max_pages must be a positive integer")

        page_configs = [
            replace(search_config, page=page_number)
            for page_number in range(
                search_config.page,
                search_config.page + max_pages,
            )
        ]
        urls = [self.build_search_url(config) for config in page_configs]
        for url in urls:
            self.record_request(url)

        loader_results = self.run_with_retry(
            lambda: self._load_listing_pages(urls),
            operation_name="autoscout24 listing page batch load",
        )
        return [
            _loaded_page_from_batch_result(
                search_config=config,
                result=result,
                metadata_builder=self.build_raw_metadata,
            )
            for config, result in zip(page_configs, loader_results, strict=True)
        ]

    def collect(self) -> list[LoadedListingPage]:
        """Return no records because this foundation requires explicit searches."""
        return []

    def _load_listing_pages(self, urls: list[str]) -> list[PageLoadResult]:
        batch_loader = getattr(self._page_loader, "load_listing_pages", None)
        if batch_loader is not None:
            return batch_loader(
                urls,
                timeout_seconds=self.runtime_settings.request_timeout_seconds,
            )

        results: list[PageLoadResult] = []
        for url in urls:
            try:
                html = self._page_loader.load_listing_page(
                    url,
                    timeout_seconds=self.runtime_settings.request_timeout_seconds,
                )
                results.append(PageLoadResult(url=url, html=html))
            except Exception as exc:
                results.append(
                    PageLoadResult(
                        url=url,
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                )
        return results


def _validate_german_autoscout24_source(base_url: str | None) -> None:
    if base_url is None:
        raise CollectorConfigurationError("AutoScout24 Germany base_url is required")
    try:
        build_search_url(SearchConfig(brand="Volkswagen"), base_url=base_url)
    except ValueError as exc:
        raise CollectorConfigurationError(
            f"AutoScout24 collector only supports German AutoScout24: {base_url}"
        ) from exc


def _loaded_page_from_batch_result(
    *,
    search_config: SearchConfig,
    result: PageLoadResult,
    metadata_builder: Callable[[str, str], RawCollectionMetadata],
) -> LoadedListingPage | ListingPageLoadFailure:
    if result.succeeded and result.html is not None:
        return LoadedListingPage(
            search_config=search_config,
            url=result.url,
            html=result.html,
            metadata=metadata_builder(result.url, result.html),
        )
    return ListingPageLoadFailure(
        search_config=search_config,
        url=result.url,
        error_message=result.error_message or "Unknown AutoScout24 page load error",
    )
