"""Generate the standalone Germany Automotive Executive Brief artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for import_path in (PROJECT_ROOT, DASHBOARD_ROOT, PROJECT_ROOT / "src"):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from services.executive_brief import (  # noqa: E402
    DEFAULT_EXECUTIVE_BRIEF_PATH,
    generate_executive_brief_artifact,
)
from services.intelligence import load_daily_market_intelligence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    """Generate one evidence-grounded Markdown brief and print its status."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate the Germany Automotive Executive Brief from current "
            "read-only Project Germania intelligence artifacts."
        )
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EXECUTIVE_BRIEF_PATH,
    )
    parser.add_argument(
        "--demo-mode",
        action="store_true",
        help="Read bundled Demo artifacts; the output path remains explicit.",
    )
    parser.add_argument(
        "--no-live-external",
        action="store_true",
        help="Use the validated Content Feed without live network calls.",
    )
    args = parser.parse_args(argv)
    if args.demo_mode:
        os.environ["DEMO_MODE"] = "true"
    if args.no_live_external:
        os.environ["LIVE_EXTERNAL_INTELLIGENCE"] = "false"

    report = load_daily_market_intelligence(args.input)
    brief, output = generate_executive_brief_artifact(
        report,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "report_date": brief.report_date,
                "output": str(output),
                "generation_mode": brief.generation_mode,
                "provider": brief.provider_name,
                "confidence": brief.confidence_level,
                "evidence_sha256": brief.evidence_sha256,
                "internal_evidence_count": len(brief.internal_evidence),
                "external_signal_count": len(brief.external_evidence),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
