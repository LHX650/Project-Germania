"""Command-line entry point for the daily market-intelligence report."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import URL

from germania.analytics import (
    build_daily_market_intelligence,
    write_daily_market_intelligence,
)
from germania.db import create_database_engine, create_session_factory

DEFAULT_DATABASE_PATH = Path("database/project_germania_live.sqlite3")
DEFAULT_OUTPUT_PATH = Path("reports/daily_market_intelligence.json")


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the read-only daily analytics JSON report."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    database_path = args.database_path.resolve()
    if not database_path.is_file():
        parser.error(f"database does not exist: {database_path}")

    database_url = URL.create("sqlite+pysqlite", database=str(database_path))
    engine = create_database_engine(database_url.render_as_string(hide_password=False))
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            report = build_daily_market_intelligence(
                session,
                report_date=args.report_date,
            )
        output = write_daily_market_intelligence(report, args.output)
    finally:
        engine.dispose()
    print(output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate read-only Project Germania market intelligence JSON."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Existing Project Germania SQLite database path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSON path.",
    )
    parser.add_argument(
        "--date",
        dest="report_date",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="Report date in YYYY-MM-DD (default: current UTC date).",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
