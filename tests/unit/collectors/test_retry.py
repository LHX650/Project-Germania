from __future__ import annotations

import pytest

from germania.collectors.exceptions import CollectorTransientError
from germania.collectors.retry import RetryPolicy, run_with_retry


def test_run_with_retry_returns_after_transient_failures() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []
    policy = RetryPolicy(
        max_attempts=3,
        initial_backoff_seconds=0.5,
        backoff_multiplier=2,
        max_backoff_seconds=10,
    )

    def operation() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise CollectorTransientError("temporary test failure")
        return "ok"

    result = run_with_retry(operation, policy, sleep=sleeps.append)

    assert result == "ok"
    assert len(attempts) == 3
    assert sleeps == [0.5, 1.0]


def test_run_with_retry_reraises_after_attempts_exhausted() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []
    policy = RetryPolicy(
        max_attempts=2,
        initial_backoff_seconds=1,
        backoff_multiplier=2,
        max_backoff_seconds=10,
    )

    def operation() -> str:
        attempts.append(1)
        raise CollectorTransientError("still failing")

    with pytest.raises(CollectorTransientError, match="still failing"):
        run_with_retry(operation, policy, sleep=sleeps.append)

    assert len(attempts) == 2
    assert sleeps == [1]


def test_run_with_retry_does_not_retry_non_retryable_error() -> None:
    attempts: list[int] = []
    policy = RetryPolicy(
        max_attempts=3,
        initial_backoff_seconds=1,
        backoff_multiplier=2,
        max_backoff_seconds=10,
    )

    def operation() -> str:
        attempts.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError, match="not retryable"):
        run_with_retry(operation, policy)

    assert len(attempts) == 1


def test_retry_policy_caps_backoff_delay() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        initial_backoff_seconds=2,
        backoff_multiplier=3,
        max_backoff_seconds=5,
    )

    assert policy.delay_after_failure(1) == 2
    assert policy.delay_after_failure(2) == 5
    assert policy.delay_after_failure(3) == 5
