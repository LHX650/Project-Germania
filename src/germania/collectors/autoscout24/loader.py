"""Page loader interface for German AutoScout24 listing HTML."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from germania.collectors.browser import BrowserManager

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = frozenset({"image", "font", "media"})
_ALLOWED_AUTOSCOUT24_HOSTS = frozenset({"autoscout24.de", "www.autoscout24.de"})
_COOKIE_ACCEPT_SELECTORS = (
    "button[data-testid='uc-accept-all-button']",
    "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')",
)
_LISTING_PAGE_MARKERS = (
    'data-testid="listing-card"',
    'data-testid="list-item"',
    "data-listing-id=",
)
_BLOCKED_PAGE_TITLE_TERMS = (
    "access denied",
    "attention required",
    "just a moment",
    "request blocked",
)
_CHALLENGE_PAGE_MARKERS = (
    "cf-chl-",
    'id="challenge-form"',
    "captcha-container",
    "verify you are human",
    "unusual traffic",
)
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


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
        self._batch_page: object | None = None

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        """Load a listing page and return its raw HTML without parsing it."""
        page = self._browser_manager.new_page()
        timeout_ms = round(timeout_seconds * 1000)
        self._logger.info("Loading AutoScout24 listing page url=%s", url)

        try:
            return (
                _navigate_and_read_page(
                    page,
                    url,
                    timeout_ms=timeout_ms,
                    loader_logger=self._logger,
                ).html
                or ""
            )
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
        page = self._batch_page
        if page is None:
            page = self._browser_manager.new_page()
            _install_resource_blocking(page)
            self._batch_page = page
        timeout_ms = round(timeout_seconds * 1000)
        results: list[PageLoadResult] = []

        for url in urls:
            self._logger.info("Loading AutoScout24 batch listing page url=%s", url)
            try:
                results.append(
                    _navigate_and_read_page(
                        page,
                        url,
                        timeout_ms=timeout_ms,
                        loader_logger=self._logger,
                    )
                )
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self._logger.warning(
                    "AutoScout24 batch page failed url=%s error=%s",
                    url,
                    error_message,
                )
                results.append(PageLoadResult(url=url, error_message=error_message))

        return results

    def close(self) -> None:
        """Close the reusable batch page, if one was opened."""
        page, self._batch_page = self._batch_page, None
        close = getattr(page, "close", None)
        if close is not None:
            close()


def _install_resource_blocking(page: object) -> None:
    route = getattr(page, "route", None)
    if route is None:
        return
    route("**/*", _handle_route)


def _navigate_and_read_page(
    page: object,
    requested_url: str,
    *,
    timeout_ms: int,
    loader_logger: logging.Logger,
) -> PageLoadResult:
    response = page.goto(
        requested_url,
        wait_until="domcontentloaded",
        timeout=timeout_ms,
    )
    _accept_cookie_banner(page, loader_logger)
    html = str(page.content())
    final_url = _page_url(page, requested_url)
    status_code = _response_status(response)
    _validate_loaded_page(
        requested_url=requested_url,
        final_url=final_url,
        status_code=status_code,
        html=html,
    )
    loader_logger.info(
        "Loaded AutoScout24 page requested_url=%s final_url=%s status=%s bytes=%s",
        requested_url,
        final_url,
        status_code if status_code is not None else "unknown",
        len(html.encode("utf-8")),
    )
    return PageLoadResult(url=final_url, html=html)


def _accept_cookie_banner(page: object, loader_logger: logging.Logger) -> None:
    locator_factory = getattr(page, "locator", None)
    if locator_factory is None:
        return

    for selector in _COOKIE_ACCEPT_SELECTORS:
        try:
            locator = locator_factory(selector)
            locator = getattr(locator, "first", locator)
            is_visible = getattr(locator, "is_visible", None)
            if is_visible is None or not is_visible(timeout=500):
                continue
            locator.click(timeout=2000)
            loader_logger.info(
                "Accepted AutoScout24 cookie banner selector=%s",
                selector,
            )
            return
        except Exception as exc:
            loader_logger.debug(
                "AutoScout24 cookie selector unavailable selector=%s error=%s",
                selector,
                exc,
            )


def _validate_loaded_page(
    *,
    requested_url: str,
    final_url: str,
    status_code: int | None,
    html: str,
) -> None:
    if status_code is not None and status_code >= 400:
        raise RuntimeError(
            f"AutoScout24 returned HTTP {status_code} for {requested_url}"
        )

    parsed_final_url = urlparse(final_url)
    if (
        parsed_final_url.scheme != "https"
        or parsed_final_url.hostname not in _ALLOWED_AUTOSCOUT24_HOSTS
        or not parsed_final_url.path.startswith("/lst/")
    ):
        raise RuntimeError(
            "AutoScout24 search was redirected to an unexpected page: "
            f"requested={requested_url} final={final_url}"
        )

    normalized_html = html.casefold()
    title_match = _TITLE_PATTERN.search(html)
    title = title_match.group(1).strip().casefold() if title_match else ""
    if any(term in title for term in _BLOCKED_PAGE_TITLE_TERMS):
        raise RuntimeError(f"AutoScout24 returned a blocked page title: {title}")

    has_listing_markup = any(
        marker in normalized_html for marker in _LISTING_PAGE_MARKERS
    )
    has_challenge_markup = any(
        marker in normalized_html for marker in _CHALLENGE_PAGE_MARKERS
    )
    if has_challenge_markup and not has_listing_markup:
        raise RuntimeError("AutoScout24 returned a CAPTCHA or access challenge page")


def _page_url(page: object, fallback: str) -> str:
    value = getattr(page, "url", fallback)
    if callable(value):
        value = value()
    return str(value or fallback)


def _response_status(response: object | None) -> int | None:
    if response is None:
        return None
    value = getattr(response, "status", None)
    if callable(value):
        value = value()
    return value if isinstance(value, int) else None


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
