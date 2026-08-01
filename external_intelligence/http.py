"""Bounded standard-library HTTP client for public external sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HTTPResponse:
    """Minimal response required by the cache and providers."""

    body: bytes
    status_code: int
    content_type: str
    etag: str | None = None
    last_modified: str | None = None


class HTTPFetcher(Protocol):
    """Replaceable HTTP boundary used by offline tests."""

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> HTTPResponse:
        """Fetch one public resource with a bounded response size."""


class UrllibHTTPFetcher:
    """Small no-auth HTTP client with timeout and response-size limits."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        user_agent: str,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0:
            raise ValueError("HTTP timeout and max_bytes must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.user_agent = user_agent

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> HTTPResponse:
        """Fetch one HTTPS resource without authentication or unbounded retries."""

        if not url.startswith("https://"):
            raise ValueError("external source URL must use HTTPS")
        request_headers = {
            "Accept": "application/rss+xml, application/atom+xml, application/xml, "
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, "
            "text/html;q=0.9, */*;q=0.5",
            "User-Agent": self.user_agent,
            **(headers or {}),
        }
        request = Request(url, headers=request_headers)
        try:
            response = urlopen(request, timeout=self.timeout_seconds)  # noqa: S310
        except HTTPError as exc:
            if exc.code == 304:
                return HTTPResponse(b"", 304, "", exc.headers.get("ETag"))
            raise
        with response:
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError(
                    f"external response exceeds {self.max_bytes} byte limit"
                )
            return HTTPResponse(
                body=body,
                status_code=int(response.status),
                content_type=response.headers.get_content_type(),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
