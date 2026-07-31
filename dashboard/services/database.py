"""Read-only database access foundation for future dashboard phases."""

from __future__ import annotations

from pathlib import Path
import sqlite3


DEFAULT_DATABASE_RELATIVE_PATH = Path("database/project_germania_live.sqlite3")


def get_project_root() -> Path:
    """Return the absolute Project Germania root directory."""

    return Path(__file__).resolve().parents[2]


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    """Resolve a database path without creating a file or opening a connection."""

    candidate = (
        Path(database_path).expanduser()
        if database_path is not None
        else DEFAULT_DATABASE_RELATIVE_PATH
    )
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return candidate.resolve(strict=False)


def database_exists(database_path: str | Path | None = None) -> bool:
    """Return whether the resolved SQLite database is an existing file."""

    return resolve_database_path(database_path).is_file()


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open an existing SQLite database with URI-enforced read-only access.

    The function never creates a missing database. Phase 17A defines this
    interface but does not call it from any page.
    """

    resolved_path = resolve_database_path(database_path)
    if not resolved_path.is_file():
        raise FileNotFoundError(
            "Project Germania SQLite database was not found at "
            f"'{resolved_path}'. A database file will not be created automatically."
        )

    read_only_uri = f"{resolved_path.as_uri()}?mode=ro"
    return sqlite3.connect(read_only_uri, uri=True)
