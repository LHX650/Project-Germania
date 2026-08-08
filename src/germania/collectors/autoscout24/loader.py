"""Page loader interface for German AutoScout24 listing HTML."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse

from germania.collectors.browser import BrowserManager
from germania.collectors.exceptions import CollectorAccessDeniedError

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

    def preflight(self, url: str, *, timeout_seconds: float) -> None:
        """Confirm source access before a collection batch starts."""


class PlaywrightPageLoader:
    """PageLoader implementation backed by the shared BrowserManager."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        *,
        min_delay_seconds: float = 0,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        stop_on_access_denied: bool = True,
        access_denied_callback: (
            Callable[[CollectorAccessDeniedError], None] | None
        ) = None,
        loader_logger: logging.Logger | None = None,
    ) -> None:
        if min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be non-negative")
        self._browser_manager = browser_manager
        self._logger = loader_logger or logger
        self._min_delay_seconds = min_delay_seconds
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._stop_on_access_denied = stop_on_access_denied
        self._access_denied_callback = access_denied_callback
        self._last_request_started_at: float | None = None
        self._batch_page: object | None = None

    def preflight(self, url: str, *, timeout_seconds: float) -> None:
        """Load the public source homepage without preserving its content."""

        page = self._browser_manager.new_page()
        _install_resource_blocking(page)
        timeout_ms = round(timeout_seconds * 1000)
        self._logger.info("Checking AutoScout24 source access url=%s", url)
        try:
            self._wait_for_request_interval()
            _navigate_and_read_page(
                page,
                url,
                timeout_ms=timeout_ms,
                loader_logger=self._logger,
                required_path_prefix="/",
            )
        except CollectorAccessDeniedError as exc:
            self._notify_access_denied(exc)
            raise
        finally:
            close = getattr(page, "close", None)
            if close is not None:
                close()

    def load_listing_page(self, url: str, *, timeout_seconds: float) -> str:
        """Load a listing page and return its raw HTML without parsing it."""
        page = self._browser_manager.new_page()
        timeout_ms = round(timeout_seconds * 1000)
        self._logger.info("Loading AutoScout24 listing page url=%s", url)

        try:
            self._wait_for_request_interval()
            return (
                _navigate_and_read_page(
                    page,
                    url,
                    timeout_ms=timeout_ms,
                    loader_logger=self._logger,
                ).html
                or ""
            )
        except CollectorAccessDeniedError as exc:
            self._notify_access_denied(exc)
            raise
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

        for index, url in enumerate(urls):
            self._logger.info("Loading AutoScout24 batch listing page url=%s", url)
            try:
                self._wait_for_request_interval()
                results.append(
                    _navigate_and_read_page(
                        page,
                        url,
                        timeout_ms=timeout_ms,
                        loader_logger=self._logger,
                    )
                )
            except CollectorAccessDeniedError as exc:
                self._notify_access_denied(exc)
                error_message = f"{type(exc).__name__}: {exc}"
                self._logger.warning(
                    "AutoScout24 batch access denied url=%s error=%s",
                    url,
                    error_message,
                )
                results.append(PageLoadResult(url=url, error_message=error_message))
                if self._stop_on_access_denied:
                    results.extend(
                        PageLoadResult(
                            url=skipped_url,
                            error_message=(
                                "Skipped after AutoScout24 access denial in the "
                                "current batch"
                            ),
                        )
                        for skipped_url in urls[index + 1 :]
                    )
                    break
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self._logger.warning(
                    "AutoScout24 batch page failed url=%s error=%s",
                    url,
                    error_message,
                )
                results.append(PageLoadResult(url=url, error_message=error_message))

        return results

    def _notify_access_denied(self, exc: CollectorAccessDeniedError) -> None:
        if self._access_denied_callback is not None:
            self._access_denied_callback(exc)

    def close(self) -> None:
        """Close the reusable batch page, if one was opened."""
        page, self._batch_page = self._batch_page, None
        close = getattr(page, "close", None)
        if close is not None:
            close()

    def _wait_for_request_interval(self) -> None:
        """Enforce the configured minimum interval between request starts."""

        now = self._monotonic()
        if self._last_request_started_at is not None:
            elapsed = now - self._last_request_started_at
            remaining = self._min_delay_seconds - elapsed
            if remaining > 0:
                self._sleeper(remaining)
                now = self._monotonic()
        self._last_request_started_at = now


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
    required_path_prefix: str = "/lst/",
) -> PageLoadResult:
    response = page.goto(
        requested_url,
        wait_until="domcontentloaded",
        timeout=timeout_ms,
    )
    final_url = _page_url(page, requested_url)
    status_code = _response_status(response)
    response_headers = _response_headers(response)
    if status_code == 403:
        timestamp = datetime.now(UTC).isoformat()
        server = response_headers.get("server")
        header_names = tuple(sorted(response_headers))
        loader_logger.error(
            "AutoScout24 access denied status_code=%s url=%s final_url=%s "
            "server=%s response_header_names=%s timestamp=%s",
            status_code,
            requested_url,
            final_url,
            server or "unknown",
            ",".join(header_names),
            timestamp,
        )
        raise CollectorAccessDeniedError(
            "AutoScout24 returned HTTP 403 "
            f"url={requested_url} final_url={final_url} "
            f"server={server or 'unknown'} timestamp={timestamp}"
        )
    _accept_cookie_banner(page, loader_logger)
    html = str(page.content())
    _validate_loaded_page(
        requested_url=requested_url,
        final_url=final_url,
        status_code=status_code,
        html=html,
        required_path_prefix=required_path_prefix,
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
    required_path_prefix: str = "/lst/",
) -> None:
    if status_code is not None and status_code >= 400:
        raise RuntimeError(
            f"AutoScout24 returned HTTP {status_code} for {requested_url}"
        )

    parsed_final_url = urlparse(final_url)
    if (
        parsed_final_url.scheme != "https"
        or parsed_final_url.hostname not in _ALLOWED_AUTOSCOUT24_HOSTS
        or not parsed_final_url.path.startswith(required_path_prefix)
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


def _response_headers(response: object | None) -> dict[str, str]:
    if response is None:
        return {}
    all_headers = getattr(response, "all_headers", None)
    if callable(all_headers):
        try:
            value = all_headers()
        except Exception:
            value = None
        if isinstance(value, dict):
            return {str(key).casefold(): str(item) for key, item in value.items()}
    value = getattr(response, "headers", None)
    if callable(value):
        try:
            value = value()
        except Exception:
            value = None
    if isinstance(value, dict):
        return {str(key).casefold(): str(item) for key, item in value.items()}
    return {}


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
