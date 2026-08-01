"""AI report stage gated by the upstream Analytics execution status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ai.analyst import generate_ai_market_report
from ai.models import load_analytics_input
from ai.providers import LLMProvider
from ai.reporting import write_ai_market_report

logger = logging.getLogger(__name__)

DEFAULT_ANALYTICS_INPUT = Path("reports/daily_market_intelligence.json")
DEFAULT_AI_OUTPUT = Path("reports/daily_ai_market_report.md")


@dataclass(frozen=True)
class AIStageResult:
    """Auditable result from the optional AI reporting stage."""

    analytics_status: str
    ai_status: str
    input_path: str
    output_path: str | None
    generation_mode: str | None
    provider_name: str | None
    error_message: str | None = None


def run_ai_report_stage(
    *,
    analytics_status: str,
    input_path: str | Path = DEFAULT_ANALYTICS_INPUT,
    output_path: str | Path = DEFAULT_AI_OUTPUT,
    provider: LLMProvider | None = None,
) -> AIStageResult:
    """Generate AI Markdown only when Analytics completed successfully.

    Failures are isolated and returned as status. The atomic writer ensures an
    existing valid AI report remains untouched when parsing, generation, or
    writing fails.
    """

    resolved_input = Path(input_path).expanduser().resolve(strict=False)
    if analytics_status != "completed":
        logger.warning(
            "AI report skipped analytics_status=%s ai_status=skipped input=%s",
            analytics_status,
            resolved_input,
        )
        return AIStageResult(
            analytics_status=analytics_status,
            ai_status="skipped",
            input_path=str(resolved_input),
            output_path=None,
            generation_mode=None,
            provider_name=provider.name if provider is not None else None,
        )

    try:
        analytics = load_analytics_input(resolved_input)
        generated = generate_ai_market_report(analytics, provider=provider)
        written_path = write_ai_market_report(generated, output_path)
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "AI report failed analytics_status=completed ai_status=failed error=%s",
            error_message,
        )
        return AIStageResult(
            analytics_status="completed",
            ai_status="failed",
            input_path=str(resolved_input),
            output_path=None,
            generation_mode=None,
            provider_name=provider.name if provider is not None else None,
            error_message=error_message,
        )

    logger.info(
        "AI report completed analytics_status=completed ai_status=completed "
        "generation_mode=%s output=%s",
        generated.generation_mode,
        written_path,
    )
    return AIStageResult(
        analytics_status="completed",
        ai_status="completed",
        input_path=str(resolved_input),
        output_path=str(written_path),
        generation_mode=generated.generation_mode,
        provider_name=generated.provider_name,
    )
