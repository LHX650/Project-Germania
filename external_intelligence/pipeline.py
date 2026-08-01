"""Independent external-intelligence stage for production orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ai.models import load_analytics_input
from external_intelligence.service import (
    build_provider_suite,
    write_external_intelligence_json,
)
from strategic.external import (
    ExternalIntelligenceRequest,
    collect_external_intelligence,
)

logger = logging.getLogger(__name__)
DEFAULT_EXTERNAL_OUTPUT = Path("reports/external_intelligence.json")
DEFAULT_EXTERNAL_CONFIG = Path("config/external_intelligence.yaml")


@dataclass(frozen=True)
class ExternalIntelligenceStageResult:
    """Auditable result from one public external-intelligence collection."""

    external_intelligence_status: str
    analytics_input_path: str
    output_path: str | None
    signal_count: int
    available_source_count: int
    failed_source_count: int
    error_message: str | None = None


def run_external_intelligence_stage(
    *,
    analytics_input_path: str | Path,
    output_path: str | Path = DEFAULT_EXTERNAL_OUTPUT,
    config_path: str | Path = DEFAULT_EXTERNAL_CONFIG,
) -> ExternalIntelligenceStageResult:
    """Generate external evidence without writing partial all-failure output."""

    analytics_path = Path(analytics_input_path).expanduser().resolve(strict=False)
    try:
        analytics = load_analytics_input(analytics_path)
        request = ExternalIntelligenceRequest(
            report_date=analytics.report_date,
            brands=tuple(sorted({brand.brand for brand in analytics.brands})),
            vehicles=tuple(
                sorted(
                    f"{vehicle.brand} {vehicle.model}" for vehicle in analytics.vehicles
                )
            ),
        )
        suite = build_provider_suite(config_path)
        bundle = collect_external_intelligence(
            request,
            kba_provider=suite.kba,
            news_provider=suite.news,
            brand_news_provider=suite.brand_news,
        )
        source_runs = (
            *suite.kba.source_runs,
            *suite.news.source_runs,
            *suite.brand_news.source_runs,
        )
        available_count = sum(run.status == "available" for run in source_runs)
        failed_count = sum(run.status == "failed" for run in source_runs)
        if available_count == 0:
            raise RuntimeError(
                "all configured external-intelligence sources failed; "
                "the previous artifact was preserved"
            )
        written = write_external_intelligence_json(
            suite=suite,
            bundle=bundle,
            report_date=analytics.report_date,
            output_path=output_path,
        )
        status = "partially_completed" if failed_count else "completed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("External-intelligence stage failed error=%s", error)
        return ExternalIntelligenceStageResult(
            external_intelligence_status="failed",
            analytics_input_path=str(analytics_path),
            output_path=None,
            signal_count=0,
            available_source_count=0,
            failed_source_count=0,
            error_message=error,
        )
    return ExternalIntelligenceStageResult(
        external_intelligence_status=status,
        analytics_input_path=str(analytics_path),
        output_path=str(written),
        signal_count=bundle.available_signal_count,
        available_source_count=available_count,
        failed_source_count=failed_count,
        error_message=(
            f"{failed_count} external source(s) failed; see source limitations "
            "in reports/external_intelligence.json"
            if failed_count
            else None
        ),
    )
