"""Database configuration helpers for local tooling."""

from __future__ import annotations

import os
from collections.abc import Mapping

GERMANIA_DATABASE_URL_ENV = "GERMANIA_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///database/germania_dev.sqlite3"
_PLACEHOLDER_DATABASE_URLS = {""}


def get_database_url(
    config_url: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the database URL for Alembic and local database tooling.

    Priority order:
    1. ``GERMANIA_DATABASE_URL`` environment variable.
    2. ``sqlalchemy.url`` from ``alembic.ini``.
    3. Safe local SQLite development default.
    """

    values = environ if environ is not None else os.environ
    env_url = values.get(GERMANIA_DATABASE_URL_ENV, "").strip()
    if env_url:
        return env_url

    ini_url = (config_url or "").strip()
    if ini_url not in _PLACEHOLDER_DATABASE_URLS:
        return ini_url

    return DEFAULT_DATABASE_URL
