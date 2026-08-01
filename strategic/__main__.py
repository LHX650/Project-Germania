"""CLI for independent Project Germania strategic reporting."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from strategic.pipeline import (
    DEFAULT_AI_INPUT,
    DEFAULT_ANALYTICS_INPUT,
    DEFAULT_EXTERNAL_OUTPUT,
    DEFAULT_STRATEGIC_OUTPUT,
    run_strategic_report_stage,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a strategic report with configured public external providers."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate an independent strategic market report from existing "
            "Analytics and AI artifacts."
        )
    )
    parser.add_argument("--analytics-input", type=Path, default=DEFAULT_ANALYTICS_INPUT)
    parser.add_argument("--ai-input", type=Path, default=DEFAULT_AI_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_STRATEGIC_OUTPUT)
    parser.add_argument(
        "--external-config",
        type=Path,
        default=Path("config/external_intelligence.yaml"),
    )
    parser.add_argument(
        "--external-output",
        type=Path,
        default=DEFAULT_EXTERNAL_OUTPUT,
    )
    parser.add_argument(
        "--external-input",
        type=Path,
        help="Use an existing validated external-intelligence artifact.",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="Generate from Analytics and AI only, without external HTTP requests.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run_strategic_report_stage(
        analytics_input_path=args.analytics_input,
        ai_input_path=args.ai_input,
        output_path=args.output,
        enable_external_providers=not args.no_external,
        external_config_path=args.external_config,
        external_output_path=args.external_output,
        external_input_path=args.external_input,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0 if result.strategic_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
