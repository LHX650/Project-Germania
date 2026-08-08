"""CLI entry point for the complete automated intelligence pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from pipeline.orchestrator import (
    DEFAULT_AI_REPORT,
    DEFAULT_ANALYTICS_REPORT,
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_CONTENT_FEED_REPORT,
    DEFAULT_EXECUTIVE_BRIEF_REPORT,
    DEFAULT_EXTERNAL_INTELLIGENCE_REPORT,
    DEFAULT_STATUS_OUTPUT,
    DEFAULT_STRATEGIC_REPORT,
    run_intelligence_pipeline,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the full pipeline and return non-zero when any stage fails."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the unchanged daily monitor, then AI, External Intelligence, "
            "Content Feed, Executive Brief, and Strategic reporting with atomic "
            "status and "
            "prior-report version archives."
        )
    )
    parser.add_argument(
        "--analytics-report", type=Path, default=DEFAULT_ANALYTICS_REPORT
    )
    parser.add_argument("--ai-report", type=Path, default=DEFAULT_AI_REPORT)
    parser.add_argument(
        "--external-intelligence-report",
        type=Path,
        default=DEFAULT_EXTERNAL_INTELLIGENCE_REPORT,
    )
    parser.add_argument(
        "--content-feed-report",
        type=Path,
        default=DEFAULT_CONTENT_FEED_REPORT,
    )
    parser.add_argument(
        "--executive-brief-report",
        type=Path,
        default=DEFAULT_EXECUTIVE_BRIEF_REPORT,
    )
    parser.add_argument(
        "--strategic-report", type=Path, default=DEFAULT_STRATEGIC_REPORT
    )
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS_OUTPUT)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("collection_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    collection_args = list(args.collection_args)
    if collection_args[:1] == ["--"]:
        collection_args = collection_args[1:]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = run_intelligence_pipeline(
            collection_args,
            analytics_report_path=args.analytics_report,
            ai_report_path=args.ai_report,
            external_intelligence_report_path=args.external_intelligence_report,
            content_feed_report_path=args.content_feed_report,
            executive_brief_report_path=args.executive_brief_report,
            strategic_report_path=args.strategic_report,
            status_output_path=args.status_output,
            archive_root=args.archive_root,
        )
    except ValueError as exc:
        logger = logging.getLogger(__name__)
        logger.error("Invalid pipeline arguments: %s", exc)
        return 2
    if result.collection_stderr:
        sys.stderr.write(result.collection_stderr)
    print(json.dumps(result.status.to_dict(), ensure_ascii=False, indent=2))
    return (
        0
        if result.status.pipeline_status in {"completed", "partially_completed"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
