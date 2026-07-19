"""Export marketplace SQLite data to Excel and CSV."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from germania.db import create_database_engine, create_session_factory
from germania.marketplace_exports import export_marketplace_data


def main() -> int:
    """Run a read-only marketplace export and print its result."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            result = export_marketplace_data(session, arguments.output_dir)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export marketplace listings and summaries from SQLite."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
