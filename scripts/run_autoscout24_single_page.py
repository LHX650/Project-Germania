"""Run one compliant AutoScout24 search-result page through the local pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from germania.collectors.autoscout24 import (
    AutoScout24Collector,
    AutoScout24SinglePagePipeline,
    SearchConfig,
)
from germania.db import create_database_engine, create_session_factory, session_scope


def main() -> int:
    """Collect and process one AutoScout24 Germany search-result page."""

    arguments = _parse_arguments()
    engine = create_database_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            result = AutoScout24SinglePagePipeline(
                AutoScout24Collector(),
                session,
            ).run(
                SearchConfig(brand=arguments.brand, model=arguments.model),
                raw_html_path=arguments.raw_html_path,
                mode=arguments.mode,
            )
        print(json.dumps(_json_result(asdict(result)), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()
    return 0


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect exactly one AutoScout24 Germany result page.",
    )
    parser.add_argument("--mode", choices=("dry_run", "import"), required=True)
    parser.add_argument("--raw-html-path", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--brand", default="Volkswagen")
    parser.add_argument("--model", default="Golf")
    return parser.parse_args()


def _json_result(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_result(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
