"""CLI for generating a grounded AI market report without a paid API."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from ai.pipeline import (
    DEFAULT_AI_OUTPUT,
    DEFAULT_ANALYTICS_INPUT,
    run_ai_report_stage,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standalone AI reporting stage and print structured status JSON."""

    parser = argparse.ArgumentParser(
        description=(
            "Convert daily_market_intelligence.json into a grounded Markdown "
            "market report using local rules by default."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_ANALYTICS_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_AI_OUTPUT)
    parser.add_argument(
        "--analytics-status",
        choices=("completed", "failed", "partially_completed", "skipped"),
        default="completed",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run_ai_report_stage(
        analytics_status=args.analytics_status,
        input_path=args.input,
        output_path=args.output,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 1 if result.ai_status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
