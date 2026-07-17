"""Logging configuration helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(
    log_level: str | None = None,
    log_file: Path | None = None,
) -> None:
    """Configure root logging for local application runs."""
    level_name = (log_level or os.getenv("LOG_LEVEL") or "INFO").upper()
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {level_name}")

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=DEFAULT_LOG_FORMAT,
        handlers=handlers,
        force=True,
    )
