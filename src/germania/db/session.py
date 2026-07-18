"""SQLAlchemy session factory and transaction helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from germania.db.engine import create_database_engine


def create_session_factory(
    engine: Engine | None = None,
    database_url: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    autoflush: bool = True,
    expire_on_commit: bool = False,
    **session_options: Any,
) -> sessionmaker[Session]:
    """Create a SQLAlchemy session factory for explicit application use."""

    bind = engine
    if bind is None:
        bind = create_database_engine(database_url, environ=environ)

    return sessionmaker(
        bind=bind,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
        **session_options,
    )


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional session scope.

    Successful blocks are committed. Exceptions trigger rollback and are
    re-raised. Sessions are always closed before the context exits.
    """

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
