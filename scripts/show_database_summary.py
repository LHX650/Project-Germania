"""Show read-only marketplace database summary statistics."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from germania.db import create_database_engine, create_session_factory, session_scope
from germania.db.marketplace_statistics import get_marketplace_database_summary


def main() -> int:
    """Query and print marketplace totals and grouped listing counts."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            summary = get_marketplace_database_summary(session)
        print(
            json.dumps(
                asdict(summary), default=_json_default, ensure_ascii=False, indent=2
            )
        )
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show marketplace database summary.")
    parser.add_argument("--database-url")
    return parser.parse_args()


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal | date | datetime):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
