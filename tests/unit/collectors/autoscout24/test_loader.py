from __future__ import annotations

from typing import Any

from germania.collectors.autoscout24 import PlaywrightPageLoader


def test_playwright_page_loader_uses_browser_page_and_returns_html() -> None:
    browser_manager = FakeBrowserManager("<html><body>listing shell</body></html>")
    loader = PlaywrightPageLoader(browser_manager)

    html = loader.load_listing_page(
        "https://www.autoscout24.de/lst/volkswagen/golf?atype=C&cy=D",
        timeout_seconds=12.5,
    )

    assert html == "<html><body>listing shell</body></html>"
    assert browser_manager.page is not None
    assert browser_manager.page.goto_kwargs == {
        "url": "https://www.autoscout24.de/lst/volkswagen/golf?atype=C&cy=D",
        "wait_until": "domcontentloaded",
        "timeout": 12500,
    }
    assert browser_manager.page.closed is True


class FakeBrowserManager:
    def __init__(self, html: str) -> None:
        self.html = html
        self.page: FakePage | None = None

    def new_page(self) -> FakePage:
        self.page = FakePage(self.html)
        return self.page


class FakePage:
    def __init__(self, html: str) -> None:
        self.html = html
        self.goto_kwargs: dict[str, Any] | None = None
        self.closed = False

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.goto_kwargs = {
            "url": url,
            "wait_until": wait_until,
            "timeout": timeout,
        }

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True
