"""Run a bounded AutoScout24 batch collection workflow."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from germania.collectors.autoscout24 import (
    AutoScout24BatchCollectionPipeline,
    AutoScout24Collector,
    SearchConfig,
)
from germania.db import create_database_engine, create_session_factory, session_scope


def main() -> int:
    """Collect and process a bounded AutoScout24 Germany page batch."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            result = AutoScout24BatchCollectionPipeline(
                AutoScout24Collector(),
                session,
            ).run(
                SearchConfig(brand=arguments.brand, model=arguments.model),
                raw_html_dir=arguments.raw_html_dir,
                max_pages=arguments.max_pages,
                mode=arguments.mode,
            )
        print(json.dumps(_json_result(asdict(result)), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a bounded AutoScout24 Germany result-page batch.",
    )
    parser.add_argument("--mode", choices=("dry_run", "import"), required=True)
    parser.add_argument("--raw-html-dir", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--brand", default="Volkswagen")
    parser.add_argument("--model", default="Golf")
    parser.add_argument("--max-pages", type=int, default=3)
    return parser.parse_args()


def _json_result(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_result(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_result(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
