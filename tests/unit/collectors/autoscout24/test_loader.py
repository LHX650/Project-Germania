from __future__ import annotations

import logging
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


def test_batch_loader_stops_after_first_http_access_denied_and_logs_safely(
    caplog: Any,
) -> None:
    urls = [
        "https://www.autoscout24.de/lst/volkswagen/golf?page=1",
        "https://www.autoscout24.de/lst/volkswagen/golf?page=2",
        "https://www.autoscout24.de/lst/volkswagen/golf?page=3",
    ]
    browser_manager = FakeBrowserManager(
        "<title>Access Denied</title>",
        status=403,
        response_headers={
            "server": "edge-gateway",
            "set-cookie": "private-cookie-value",
            "x-request-id": "request-123",
        },
    )
    loader = PlaywrightPageLoader(
        browser_manager,
        stop_on_access_denied=True,
    )

    with caplog.at_level(logging.ERROR):
        results = loader.load_listing_pages(urls, timeout_seconds=5)
        loader.close()

    assert len(results) == 3
    assert results[0].succeeded is False
    assert results[0].error_message is not None
    assert "HTTP 403" in results[0].error_message
    assert all("Skipped after" in (item.error_message or "") for item in results[1:])
    assert browser_manager.page is not None
    assert browser_manager.page.goto_urls == [urls[0]]
    diagnostic = " ".join(record.getMessage() for record in caplog.records)
    assert "status_code=403" in diagnostic
    assert f"url={urls[0]}" in diagnostic
    assert f"final_url={urls[0]}" in diagnostic
    assert "server=edge-gateway" in diagnostic
    assert "response_header_names=server,set-cookie,x-request-id" in diagnostic
    assert "timestamp=" in diagnostic
    assert "private-cookie-value" not in diagnostic
    assert "request-123" not in diagnostic


def test_preflight_accepts_normal_homepage_response() -> None:
    url = "https://www.autoscout24.de/"
    browser_manager = FakeBrowserManager(
        "<html><body>AutoScout24</body></html>",
        status=200,
    )
    loader = PlaywrightPageLoader(browser_manager)

    loader.preflight(url, timeout_seconds=5)

    assert browser_manager.page is not None
    assert browser_manager.page.goto_urls == [url]
    assert browser_manager.page.closed is True


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


def test_batch_loader_enforces_minimum_interval_between_request_starts() -> None:
    urls = [
        "https://www.autoscout24.de/lst/volkswagen/golf?page=1",
        "https://www.autoscout24.de/lst/volkswagen/golf?page=2",
    ]
    clock = FakeClock()
    loader = PlaywrightPageLoader(
        FakeBrowserManager("<html><body>listing shell</body></html>"),
        min_delay_seconds=2.5,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )

    results = loader.load_listing_pages(urls, timeout_seconds=5)
    loader.close()

    assert all(result.succeeded for result in results)
    assert clock.sleep_calls == [2.5]
    assert clock.current == 2.5


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


class FakeBrowserManager:
    def __init__(
        self,
        html: str,
        *,
        status: int | None = None,
        final_url: str | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        self.html = html
        self.status = status
        self.final_url = final_url
        self.response_headers = response_headers or {}
        self.page: FakePage | None = None

    def new_page(self) -> FakePage:
        self.page = FakePage(
            self.html,
            status=self.status,
            final_url=self.final_url,
            response_headers=self.response_headers,
        )
        return self.page


class FakePage:
    def __init__(
        self,
        html: str,
        *,
        status: int | None,
        final_url: str | None,
        response_headers: dict[str, str],
    ) -> None:
        self.html = html
        self.status = status
        self.url = final_url
        self.goto_kwargs: dict[str, Any] | None = None
        self.goto_urls: list[str] = []
        self.response_headers = response_headers
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
        self.goto_urls.append(url)
        if self.url is None:
            self.url = url
        return (
            FakeResponse(self.status, self.response_headers)
            if self.status is not None
            else None
        )

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self._headers = headers

    def all_headers(self) -> dict[str, str]:
        return self._headers
