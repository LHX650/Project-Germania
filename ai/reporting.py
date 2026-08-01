"""Atomic Markdown persistence for AI market intelligence reports."""

from __future__ import annotations

import logging
from pathlib import Path

from ai.analyst import GeneratedAIReport

logger = logging.getLogger(__name__)


def write_ai_market_report(
    report: GeneratedAIReport,
    output_path: str | Path,
) -> Path:
    """Atomically write a complete AI report while preserving any old report."""

    path = Path(output_path).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(report.markdown, encoding="utf-8")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    logger.info(
        "Wrote AI market report path=%s generation_mode=%s provider=%s",
        path,
        report.generation_mode,
        report.provider_name or "none",
    )
    return path
