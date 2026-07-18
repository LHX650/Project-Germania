"""Page loader interface for German AutoScout24 listing HTML."""

from __future__ import annotations

import logging
from typing import Protocol

from germania.collectors.browser import BrowserManager

logger = logging.getLogger(__name__)


class PageLoader(Protocol):
    """Interface for loading an AutoScout24 listing page as raw HTML."""

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        """Load a listing page URL and return the raw HTML."""


class PlaywrightPageLoader:
    """PageLoader implementation backed by the shared BrowserManager."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        *,
        loader_logger: logging.Logger | None = None,
    ) -> None:
        self._browser_manager = browser_manager
        self._logger = loader_logger or logger

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        """Load a listing page and return its raw HTML without parsing it."""
        page = self._browser_manager.new_page()
        timeout_ms = round(timeout_seconds * 1000)
        self._logger.info("Loading AutoScout24 listing page url=%s", url)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return str(page.content())
        finally:
            close = getattr(page, "close", None)
            if close is not None:
                close()
