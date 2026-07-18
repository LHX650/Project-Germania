"""Finite retry helpers for collector operations."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from germania.collectors.exceptions import CollectorTransientError
from germania.config.playwright import RetrySettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Validated retry policy for collector operations."""

    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float
    max_backoff_seconds: float

    @classmethod
    def from_settings(cls, settings: RetrySettings) -> RetryPolicy:
        """Create a retry policy from loaded configuration settings."""
        return cls(
            max_attempts=settings.max_attempts,
            initial_backoff_seconds=settings.initial_backoff_seconds,
            backoff_multiplier=settings.backoff_multiplier,
            max_backoff_seconds=settings.max_backoff_seconds,
        )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_backoff_seconds < 0:
            raise ValueError("max_backoff_seconds must be non-negative")

    def delay_after_failure(self, failed_attempt: int) -> float:
        """Return bounded backoff delay after a failed attempt."""
        if failed_attempt < 1:
            raise ValueError("failed_attempt must be at least 1")
        delay = self.initial_backoff_seconds * (
            self.backoff_multiplier ** (failed_attempt - 1)
        )
        return min(delay, self.max_backoff_seconds)


def run_with_retry[T](
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    operation_name: str = "collector operation",
    retry_on: tuple[type[BaseException], ...] = (CollectorTransientError,),
    sleep: Callable[[float], None] = time.sleep,
    operation_logger: logging.Logger | None = None,
) -> T:
    """Run an operation with finite retries and bounded exponential backoff."""
    active_logger = operation_logger or logger
    attempt = 1

    while True:
        try:
            return operation()
        except retry_on as exc:
            if attempt >= policy.max_attempts:
                active_logger.error(
                    "%s failed after %s attempts: %s",
                    operation_name,
                    attempt,
                    exc,
                )
                raise

            delay = policy.delay_after_failure(attempt)
            active_logger.warning(
                "%s failed on attempt %s/%s; retrying in %.2fs: %s",
                operation_name,
                attempt,
                policy.max_attempts,
                delay,
                exc,
            )
            sleep(delay)
            attempt += 1
