"""Page loader interface for German AutoScout24 listing HTML."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from germania.collectors.browser import BrowserManager

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = frozenset({"image", "font", "media"})


@dataclass(frozen=True)
class PageLoadResult:
    """Raw HTML or failure details for one requested listing page."""

    url: str
    html: str | None = None
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether this page produced raw HTML."""
        return self.html is not None and self.error_message is None


class PageLoader(Protocol):
    """Interface for loading an AutoScout24 listing page as raw HTML."""

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        """Load a listing page URL and return the raw HTML."""

    def load_listing_pages(
        self,
        urls: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> list[PageLoadResult]:
        """Load multiple listing page URLs and return per-page results."""


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

    def load_listing_pages(
        self,
        urls: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> list[PageLoadResult]:
        """Load listing pages with one reused Playwright page."""
        page = self._browser_manager.new_page()
        timeout_ms = round(timeout_seconds * 1000)
        _install_resource_blocking(page)
        results: list[PageLoadResult] = []

        try:
            for url in urls:
                self._logger.info("Loading AutoScout24 batch listing page url=%s", url)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    results.append(PageLoadResult(url=url, html=str(page.content())))
                except Exception as exc:
                    error_message = f"{type(exc).__name__}: {exc}"
                    self._logger.warning(
                        "AutoScout24 batch page failed url=%s error=%s",
                        url,
                        error_message,
                    )
                    results.append(PageLoadResult(url=url, error_message=error_message))
        finally:
            close = getattr(page, "close", None)
            if close is not None:
                close()

        return results


def _install_resource_blocking(page: object) -> None:
    route = getattr(page, "route", None)
    if route is None:
        return
    route("**/*", _handle_route)


def _handle_route(route: object) -> None:
    request = getattr(route, "request", None)
    if callable(request):
        request = request()
    resource_type = getattr(request, "resource_type", None)
    if callable(resource_type):
        resource_type = resource_type()

    if resource_type in _BLOCKED_RESOURCE_TYPES:
        route.abort()
        return

    route.continue_()
