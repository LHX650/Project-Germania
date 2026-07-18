"""Playwright browser lifecycle management."""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import TracebackType
from typing import Any

from germania.collectors.exceptions import CollectorDependencyError, CollectorError
from germania.config.playwright import PlaywrightSettings

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage a single Playwright browser and context for a collection run."""

    def __init__(
        self,
        settings: PlaywrightSettings,
        *,
        playwright_factory: Callable[[], Any] | None = None,
        manager_logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._playwright_factory = playwright_factory
        self._logger = manager_logger or logger
        self._playwright_manager: Any | None = None
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None

    def __enter__(self) -> BrowserManager:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def is_started(self) -> bool:
        """Return whether the underlying browser is currently started."""
        return self._browser is not None

    def start(self) -> None:
        """Start Playwright and launch the configured browser."""
        if self._browser is not None:
            return

        try:
            self._playwright = self._load_playwright()
            browser_type = getattr(
                self._playwright,
                self._settings.browser.browser_type,
                None,
            )
            if browser_type is None:
                raise CollectorError(
                    "Configured browser type is unavailable: "
                    f"{self._settings.browser.browser_type}"
                )

            launch_options: dict[str, object] = {
                "headless": self._settings.browser.headless,
                "timeout": self._settings.browser.launch_timeout_ms,
            }
            if self._settings.browser.slow_mo_ms:
                launch_options["slow_mo"] = self._settings.browser.slow_mo_ms

            self._logger.info(
                "Launching Playwright browser type=%s headless=%s",
                self._settings.browser.browser_type,
                self._settings.browser.headless,
            )
            self._browser = browser_type.launch(**launch_options)
        except Exception:
            self.close()
            raise

    def new_context(self) -> Any:
        """Create or return the managed Playwright browser context."""
        if self._context is not None:
            return self._context
        if self._browser is None:
            self.start()

        assert self._browser is not None
        context = self._browser.new_context(**self._settings.browser.context_options())
        context.set_default_navigation_timeout(
            self._settings.browser.navigation_timeout_ms
        )
        context.set_default_timeout(self._settings.browser.action_timeout_ms)
        self._context = context
        return context

    def new_page(self) -> Any:
        """Create a new page from the managed browser context."""
        context = self.new_context()
        page = context.new_page()
        page.set_default_navigation_timeout(
            self._settings.browser.navigation_timeout_ms
        )
        page.set_default_timeout(self._settings.browser.action_timeout_ms)
        return page

    def close(self) -> None:
        """Close context, browser, and Playwright manager idempotently."""
        context, self._context = self._context, None
        browser, self._browser = self._browser, None
        playwright, self._playwright = self._playwright, None
        self._playwright_manager = None

        try:
            if context is not None:
                context.close()
        finally:
            try:
                if browser is not None:
                    browser.close()
            finally:
                stop = getattr(playwright, "stop", None)
                if stop is not None:
                    stop()

    def _load_playwright(self) -> Any:
        if self._playwright_factory is not None:
            return self._playwright_factory()

        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise CollectorDependencyError(
                "Playwright is required to launch a browser. "
                'Install the project with the "browser" extra before running '
                "browser-based collectors."
            ) from exc

        self._playwright_manager = sync_playwright()
        return self._playwright_manager.start()
