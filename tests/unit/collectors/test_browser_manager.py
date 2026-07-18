from __future__ import annotations

from typing import Any

from germania.collectors.browser import BrowserManager
from germania.config.playwright import load_playwright_config


def test_browser_manager_launches_fake_browser_and_sets_timeouts() -> None:
    settings = load_playwright_config(environ={})
    fake_playwright = FakePlaywright()
    manager = BrowserManager(
        settings,
        playwright_factory=lambda: fake_playwright,
    )

    page = manager.new_page()

    assert manager.is_started is True
    assert fake_playwright.chromium.launch_kwargs == {
        "headless": True,
        "timeout": 30000,
    }
    assert fake_playwright.browser is not None
    assert fake_playwright.browser.context_kwargs["locale"] == "de-DE"
    assert fake_playwright.browser.context_kwargs["timezone_id"] == "Europe/Berlin"
    assert fake_playwright.context is not None
    assert fake_playwright.context.navigation_timeout_ms == 30000
    assert fake_playwright.context.action_timeout_ms == 10000
    assert page.navigation_timeout_ms == 30000
    assert page.action_timeout_ms == 10000

    manager.close()

    assert manager.is_started is False
    assert fake_playwright.browser.closed is True
    assert fake_playwright.context.closed is True


def test_browser_manager_context_manager_closes_idempotently() -> None:
    settings = load_playwright_config(environ={})
    fake_playwright = FakePlaywright()

    with BrowserManager(
        settings, playwright_factory=lambda: fake_playwright
    ) as manager:
        manager.new_context()
        assert manager.is_started is True

    manager.close()

    assert manager.is_started is False
    assert fake_playwright.browser is not None
    assert fake_playwright.browser.close_count == 1
    assert fake_playwright.context is not None
    assert fake_playwright.context.close_count == 1


class FakePlaywright:
    def __init__(self) -> None:
        self.browser: FakeBrowser | None = None
        self.context: FakeContext | None = None
        self.chromium = FakeBrowserType(self)


class FakeBrowserType:
    def __init__(self, owner: FakePlaywright) -> None:
        self.owner = owner
        self.launch_kwargs: dict[str, Any] | None = None

    def launch(self, **kwargs: Any) -> FakeBrowser:
        self.launch_kwargs = kwargs
        browser = FakeBrowser(self.owner)
        self.owner.browser = browser
        return browser


class FakeBrowser:
    def __init__(self, owner: FakePlaywright) -> None:
        self.owner = owner
        self.context_kwargs: dict[str, Any] | None = None
        self.closed = False
        self.close_count = 0

    def new_context(self, **kwargs: Any) -> FakeContext:
        self.context_kwargs = kwargs
        context = FakeContext()
        self.owner.context = context
        return context

    def close(self) -> None:
        self.closed = True
        self.close_count += 1


class FakeContext:
    def __init__(self) -> None:
        self.navigation_timeout_ms: int | None = None
        self.action_timeout_ms: int | None = None
        self.closed = False
        self.close_count = 0

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        self.navigation_timeout_ms = timeout_ms

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.action_timeout_ms = timeout_ms

    def new_page(self) -> FakePage:
        return FakePage()

    def close(self) -> None:
        self.closed = True
        self.close_count += 1


class FakePage:
    def __init__(self) -> None:
        self.navigation_timeout_ms: int | None = None
        self.action_timeout_ms: int | None = None

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        self.navigation_timeout_ms = timeout_ms

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.action_timeout_ms = timeout_ms
