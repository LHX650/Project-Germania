"""Independent Executive Brief stage for the daily orchestration pipeline."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from services.ai_report import load_daily_ai_market_report  # noqa: E402
from services.content_feed import load_content_feed  # noqa: E402
from services.executive_brief import (  # noqa: E402
    generate_executive_brief_artifact,
)
from services.external_intelligence import (  # noqa: E402
    ContentFeedExternalIntelligenceProvider,
)
from services.intelligence import load_daily_market_intelligence  # noqa: E402

DEFAULT_EXECUTIVE_BRIEF_OUTPUT = Path("reports/daily_executive_intelligence_brief.md")


@dataclass(frozen=True)
class ExecutiveBriefStageResult:
    """Auditable outcome of one Executive Brief pipeline stage."""

    executive_brief_status: str
    analytics_input_path: str
    ai_input_path: str
    external_input_path: str
    content_feed_input_path: str
    output_path: str | None
    report_date: str | None
    generation_mode: str | None
    error_message: str | None = None


def run_executive_brief_stage(
    *,
    analytics_status: str,
    ai_status: str,
    external_intelligence_status: str,
    content_feed_status: str,
    analytics_input_path: str | Path,
    ai_input_path: str | Path,
    external_input_path: str | Path,
    content_feed_input_path: str | Path,
    output_path: str | Path = DEFAULT_EXECUTIVE_BRIEF_OUTPUT,
) -> ExecutiveBriefStageResult:
    """Generate one atomic Brief when all required upstream evidence is usable."""

    paths = {
        "analytics": Path(analytics_input_path).expanduser().resolve(strict=False),
        "ai": Path(ai_input_path).expanduser().resolve(strict=False),
        "external": Path(external_input_path).expanduser().resolve(strict=False),
        "content_feed": Path(content_feed_input_path)
        .expanduser()
        .resolve(strict=False),
    }
    if (
        analytics_status != "completed"
        or ai_status != "completed"
        or external_intelligence_status not in {"completed", "partially_completed"}
        or content_feed_status not in {"completed", "partially_completed"}
    ):
        return ExecutiveBriefStageResult(
            executive_brief_status="skipped",
            analytics_input_path=str(paths["analytics"]),
            ai_input_path=str(paths["ai"]),
            external_input_path=str(paths["external"]),
            content_feed_input_path=str(paths["content_feed"]),
            output_path=None,
            report_date=None,
            generation_mode=None,
            error_message=(
                "Required Analytics, AI, or External evidence is unavailable."
            ),
        )

    try:
        analytics = load_daily_market_intelligence(paths["analytics"])
        ai_report = load_daily_ai_market_report(paths["ai"])
        if ai_report.analytics_date != analytics.report_date:
            raise ValueError("AI and Analytics report dates do not match")
        _validate_external_report_date(
            paths["external"], analytics.report_date.isoformat()
        )
        feed = load_content_feed(paths["content_feed"])
        if feed.report_date != analytics.report_date:
            raise ValueError("Content Feed and Analytics report dates do not match")
        provider = ContentFeedExternalIntelligenceProvider(loader=lambda: feed)
        brief, written = generate_executive_brief_artifact(
            analytics,
            output_path=output_path,
            external_provider=provider,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("Executive Brief stage failed error=%s", error)
        return ExecutiveBriefStageResult(
            executive_brief_status="failed",
            analytics_input_path=str(paths["analytics"]),
            ai_input_path=str(paths["ai"]),
            external_input_path=str(paths["external"]),
            content_feed_input_path=str(paths["content_feed"]),
            output_path=None,
            report_date=None,
            generation_mode=None,
            error_message=error,
        )

    return ExecutiveBriefStageResult(
        executive_brief_status="completed",
        analytics_input_path=str(paths["analytics"]),
        ai_input_path=str(paths["ai"]),
        external_input_path=str(paths["external"]),
        content_feed_input_path=str(paths["content_feed"]),
        output_path=str(written),
        report_date=brief.report_date,
        generation_mode=brief.generation_mode,
    )


def _validate_external_report_date(path: Path, expected_date: str) -> None:
    """Validate the shared external artifact without assuming provider payloads."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("External Intelligence artifact is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError("External Intelligence artifact must be a JSON object")
    if payload.get("report_date") != expected_date:
        raise ValueError(
            "External Intelligence and Analytics report dates do not match"
        )
