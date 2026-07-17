from __future__ import annotations

import logging
from pathlib import Path

import pytest

from germania.utils.logging import configure_logging


def test_configure_logging_writes_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "germania.log"
    configure_logging("DEBUG", log_file)

    logger = logging.getLogger("germania.tests")
    logger.debug("health check log line")

    assert log_file.exists()
    assert "health check log line" in log_file.read_text(encoding="utf-8")


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        configure_logging("NOT_A_LEVEL")
