"""AutoScout24 Germany collector foundation."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from germania.collectors.autoscout24.config import (
    AUTOSCOUT24_DE_SOURCE_ID,
    SearchConfig,
)
from germania.collectors.autoscout24.loader import PageLoader, PlaywrightPageLoader
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

    def collect(self) -> list[LoadedListingPage]:
        """Return no records because this foundation requires explicit searches."""
        return []


def _validate_german_autoscout24_source(base_url: str | None) -> None:
    if base_url is None:
        raise CollectorConfigurationError("AutoScout24 Germany base_url is required")
    try:
        build_search_url(SearchConfig(brand="Volkswagen"), base_url=base_url)
    except ValueError as exc:
        raise CollectorConfigurationError(
            f"AutoScout24 collector only supports German AutoScout24: {base_url}"
        ) from exc
