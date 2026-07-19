"""Generate a read-only marketplace data quality workbook."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from germania.db import create_database_engine, create_session_factory
from germania.quality.marketplace import create_marketplace_quality_report


def main() -> int:
    """Run marketplace quality checks and print their summary."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            result = create_marketplace_quality_report(session, arguments.output_dir)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate marketplace data quality checks from SQLite."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
