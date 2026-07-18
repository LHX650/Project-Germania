"""Collector exception types for compliant collection workflows."""

from __future__ import annotations


class CollectorError(RuntimeError):
    """Base class for collection-layer failures."""


class CollectorConfigurationError(CollectorError):
    """Raised when collector configuration is invalid or missing."""


class CollectorDependencyError(CollectorError):
    """Raised when an optional runtime dependency is unavailable."""


class CollectorTransientError(CollectorError):
    """Raised for retryable collection failures."""


class CollectorTimeoutError(CollectorTransientError):
    """Raised when a collection operation exceeds its configured timeout."""


class CollectorAccessDeniedError(CollectorError):
    """Raised when a source denies access and collection must stop."""


class RequestBudgetExceeded(CollectorError):
    """Raised when a collector exceeds its configured per-run request budget."""
