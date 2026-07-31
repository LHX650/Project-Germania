"""Dashboard service interfaces."""

from services.database import (
    database_exists,
    get_connection,
    get_project_root,
    resolve_database_path,
)

__all__ = [
    "database_exists",
    "get_connection",
    "get_project_root",
    "resolve_database_path",
]
