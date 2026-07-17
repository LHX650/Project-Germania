from __future__ import annotations

from germania import __version__
from germania.health import HealthStatus, get_health_status


def test_get_health_status_returns_ok() -> None:
    status = get_health_status()

    assert status == HealthStatus(
        service="project-germania",
        status="ok",
        version=__version__,
    )
