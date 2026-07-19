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


def test_batch_loader_reports_http_access_denied() -> None:
    url = "https://www.autoscout24.de/lst/volkswagen/golf"
    loader = PlaywrightPageLoader(
        FakeBrowserManager("<title>Access Denied</title>", status=403)
    )

    result = loader.load_listing_pages([url], timeout_seconds=5)[0]
    loader.close()

    assert result.succeeded is False
    assert result.error_message is not None
    assert "HTTP 403" in result.error_message


def test_batch_loader_reports_unexpected_redirect() -> None:
    url = "https://www.autoscout24.de/lst/volkswagen/golf"
    loader = PlaywrightPageLoader(
        FakeBrowserManager(
            "<html><body>Login</body></html>",
            status=200,
            final_url="https://accounts.autoscout24.de/login",
        )
    )

    result = loader.load_listing_pages([url], timeout_seconds=5)[0]
    loader.close()

    assert result.succeeded is False
    assert result.error_message is not None
    assert "unexpected page" in result.error_message


def test_batch_loader_reports_captcha_without_listing_cards() -> None:
    url = "https://www.autoscout24.de/lst/volkswagen/golf"
    loader = PlaywrightPageLoader(
        FakeBrowserManager(
            '<html><body><form id="challenge-form">'
            "verify you are human</form></body></html>",
            status=200,
            final_url=url,
        )
    )

    result = loader.load_listing_pages([url], timeout_seconds=5)[0]
    loader.close()

    assert result.succeeded is False
    assert result.error_message is not None
    assert "CAPTCHA" in result.error_message


class FakeBrowserManager:
    def __init__(
        self,
        html: str,
        *,
        status: int | None = None,
        final_url: str | None = None,
    ) -> None:
        self.html = html
        self.status = status
        self.final_url = final_url
        self.page: FakePage | None = None

    def new_page(self) -> FakePage:
        self.page = FakePage(
            self.html,
            status=self.status,
            final_url=self.final_url,
        )
        return self.page


class FakePage:
    def __init__(
        self,
        html: str,
        *,
        status: int | None,
        final_url: str | None,
    ) -> None:
        self.html = html
        self.status = status
        self.url = final_url
        self.goto_kwargs: dict[str, Any] | None = None
        self.closed = False

    def goto(
        self,
        url: str,
        *,
        wait_until: str,
        timeout: int,
    ) -> FakeResponse | None:
        self.goto_kwargs = {
            "url": url,
            "wait_until": wait_until,
            "timeout": timeout,
        }
        return FakeResponse(self.status) if self.status is not None else None

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status
