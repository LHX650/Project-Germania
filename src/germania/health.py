"""Health check helpers for Project Germania."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from germania import __version__

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Local application health status."""

    service: str
    status: str
    version: str


def get_health_status() -> HealthStatus:
    """Return the current local package health status."""
    logger.debug("Generating health status")
    return HealthStatus(
        service="project-germania",
        status="ok",
        version=__version__,
    )
