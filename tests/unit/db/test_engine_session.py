from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from germania.db import create_database_engine, create_session_factory, session_scope


def test_create_database_engine_uses_settings_without_connecting(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "lazy.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"

    engine = create_database_engine(database_url)
    try:
        assert str(engine.url) == database_url
        assert not database_path.exists()
    finally:
        engine.dispose()


def test_create_database_engine_honors_environment_override(
    tmp_path: Path,
) -> None:
    configured_path = tmp_path / "configured.sqlite3"
    environment_path = tmp_path / "environment.sqlite3"
    engine = create_database_engine(
        f"sqlite+pysqlite:///{configured_path.as_posix()}",
        environ={
            "GERMANIA_DATABASE_URL": (
                f"sqlite+pysqlite:///{environment_path.as_posix()}"
            )
        },
    )

    try:
        assert str(engine.url).endswith("environment.sqlite3")
        assert not configured_path.exists()
        assert not environment_path.exists()
    finally:
        engine.dispose()


def test_sqlite_engine_enables_foreign_key_checks() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        with engine.connect() as connection:
            foreign_keys_enabled = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()
    finally:
        engine.dispose()

    assert foreign_keys_enabled == 1


def test_session_factory_binds_to_provided_engine() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        factory = create_session_factory(engine)
        session = factory()
        try:
            assert session.get_bind() is engine
            assert not session.in_transaction()
        finally:
            session.close()
    finally:
        engine.dispose()


def test_session_scope_commits_and_closes_on_success() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    _create_entries_table(engine)
    closed_sessions: list[Session] = []
    factory = _tracking_session_factory(engine, closed_sessions)

    try:
        with session_scope(factory) as session:
            session.execute(
                text("INSERT INTO entries (value) VALUES (:value)"),
                {"value": "committed"},
            )
            scoped_session = session

        assert _entry_values(engine) == ["committed"]
        assert closed_sessions == [scoped_session]
        assert not scoped_session.in_transaction()
    finally:
        engine.dispose()


def test_session_scope_rolls_back_and_closes_on_exception() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    _create_entries_table(engine)
    closed_sessions: list[Session] = []
    factory = _tracking_session_factory(engine, closed_sessions)

    try:
        with (
            pytest.raises(RuntimeError, match="rollback check"),
            session_scope(factory) as session,
        ):
            session.execute(
                text("INSERT INTO entries (value) VALUES (:value)"),
                {"value": "rolled-back"},
            )
            scoped_session = session
            raise RuntimeError("rollback check")

        assert _entry_values(engine) == []
        assert closed_sessions == [scoped_session]
        assert not scoped_session.in_transaction()
    finally:
        engine.dispose()


def _create_entries_table(engine: object) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE entries ("
                "id INTEGER PRIMARY KEY, "
                "value TEXT NOT NULL"
                ")"
            )
        )


def _entry_values(engine: object) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT value FROM entries")).scalars())


def _tracking_session_factory(
    engine: object,
    closed_sessions: list[Session],
) -> sessionmaker[Session]:
    class TrackingSession(Session):
        def close(self) -> None:
            closed_sessions.append(self)
            super().close()

    return sessionmaker(bind=engine, class_=TrackingSession)
