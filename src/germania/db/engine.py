"""SQLAlchemy engine creation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool

from germania.db.settings import get_database_url


def create_database_engine(
    database_url: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    echo: bool = False,
    pool_pre_ping: bool = True,
    connect_args: Mapping[str, Any] | None = None,
    **engine_options: Any,
) -> Engine:
    """Create a SQLAlchemy engine without opening a database connection.

    The database URL is resolved through the existing settings helper so local
    tooling and application code share the same precedence rules.
    """

    resolved_url = get_database_url(database_url, environ=environ)
    options = dict(engine_options)
    options["echo"] = echo
    options["pool_pre_ping"] = pool_pre_ping

    if connect_args is not None:
        options["connect_args"] = dict(connect_args)

    if _is_sqlite_memory_url(resolved_url):
        options.setdefault("poolclass", StaticPool)

    engine = create_engine(resolved_url, **options)
    if _is_sqlite_url(resolved_url):
        _enable_sqlite_foreign_keys(engine)

    return engine


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).drivername.startswith("sqlite")


def _is_sqlite_memory_url(database_url: str) -> bool:
    url = make_url(database_url)
    return url.drivername.startswith("sqlite") and url.database in {
        None,
        "",
        ":memory:",
    }


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
