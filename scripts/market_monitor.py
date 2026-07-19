"""Generate a read-only marketplace monitoring workbook."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from germania.db import create_database_engine, create_session_factory
from germania.market_monitoring import create_market_monitor_report


def main() -> int:
    """Compare collection windows and print market-change statistics."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            result = create_market_monitor_report(
                session,
                cutoff=arguments.cutoff,
                current_end=arguments.current_end,
                output_dir=arguments.output_dir,
            )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two marketplace collection result windows."
    )
    parser.add_argument("--database-url")
    parser.add_argument(
        "--cutoff",
        type=_iso_datetime,
        required=True,
        help="UTC timestamp separating the baseline and current collection.",
    )
    parser.add_argument(
        "--current-end",
        type=_iso_datetime,
        help="Optional inclusive UTC end of the current comparison window.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    return parser.parse_args()


def _iso_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "timestamp must use ISO 8601 format, for example 2026-07-19T03:02:00Z"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
