"""Independent strategic reporting pipeline over existing read-only artifacts."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from ai.models import DailyMarketIntelligence, load_analytics_input
from external_intelligence.artifact import load_external_intelligence_artifact
from external_intelligence.service import (
    ExternalProviderSuite,
    build_provider_suite,
    write_external_intelligence_json,
)
from strategic.ai_input import load_ai_report_evidence
from strategic.analysis import build_strategic_analysis
from strategic.external import (
    BrandNewsDataProvider,
    ExternalIntelligenceRequest,
    ExternalMarketDataProvider,
    KBADataProvider,
    NewsDataProvider,
    collect_external_intelligence,
)
from strategic.reporting import (
    render_strategic_market_report,
    write_strategic_market_report,
)

logger = logging.getLogger(__name__)
DEFAULT_ANALYTICS_INPUT = Path("reports/daily_market_intelligence.json")
DEFAULT_AI_INPUT = Path("reports/daily_ai_market_report.md")
DEFAULT_STRATEGIC_OUTPUT = Path("reports/strategic_market_report.md")
DEFAULT_EXTERNAL_OUTPUT = Path("reports/external_intelligence.json")


@dataclass(frozen=True)
class StrategicStageResult:
    """Auditable result of one independent strategic reporting run."""

    strategic_status: str
    analytics_input_path: str
    ai_input_path: str
    output_path: str | None
    external_signal_count: int
    error_message: str | None = None


def run_strategic_report_stage(
    *,
    analytics_input_path: str | Path = DEFAULT_ANALYTICS_INPUT,
    ai_input_path: str | Path = DEFAULT_AI_INPUT,
    output_path: str | Path = DEFAULT_STRATEGIC_OUTPUT,
    kba_provider: KBADataProvider | None = None,
    news_provider: NewsDataProvider | None = None,
    brand_news_provider: BrandNewsDataProvider | None = None,
    market_data_provider: ExternalMarketDataProvider | None = None,
    enable_external_providers: bool = True,
    external_config_path: str | Path = Path("config/external_intelligence.yaml"),
    external_output_path: str | Path = DEFAULT_EXTERNAL_OUTPUT,
    provider_suite: ExternalProviderSuite | None = None,
    external_input_path: str | Path | None = None,
) -> StrategicStageResult:
    """Generate a strategy report without touching collection or database code."""

    analytics_path = Path(analytics_input_path).expanduser().resolve(strict=False)
    ai_path = Path(ai_input_path).expanduser().resolve(strict=False)
    try:
        analytics = load_analytics_input(analytics_path)
        ai_report = load_ai_report_evidence(ai_path)
        if (
            ai_report.evidence_sha256 is not None
            and ai_report.evidence_sha256 != _analytics_evidence_sha256(analytics)
        ):
            raise ValueError(
                "AI report evidence SHA-256 does not match the Analytics input"
            )
        if external_input_path is not None:
            external = load_external_intelligence_artifact(
                external_input_path,
                expected_report_date=analytics.report_date,
            )
        else:
            request = ExternalIntelligenceRequest(
                report_date=analytics.report_date,
                brands=tuple(sorted({brand.brand for brand in analytics.brands})),
                vehicles=tuple(
                    sorted(
                        f"{vehicle.brand} {vehicle.model}"
                        for vehicle in analytics.vehicles
                    )
                ),
            )
        if (
            external_input_path is None
            and enable_external_providers
            and all(
                provider is None
                for provider in (
                    kba_provider,
                    news_provider,
                    brand_news_provider,
                    market_data_provider,
                )
            )
        ):
            provider_suite = provider_suite or build_provider_suite(
                external_config_path
            )
            kba_provider = provider_suite.kba
            news_provider = provider_suite.news
            brand_news_provider = provider_suite.brand_news
        if external_input_path is None:
            external = collect_external_intelligence(
                request,
                kba_provider=kba_provider,
                news_provider=news_provider,
                brand_news_provider=brand_news_provider,
                market_data_provider=market_data_provider,
            )
            if provider_suite is not None:
                write_external_intelligence_json(
                    suite=provider_suite,
                    bundle=external,
                    report_date=analytics.report_date,
                    output_path=external_output_path,
                )
        analysis = build_strategic_analysis(analytics, ai_report, external)
        markdown = render_strategic_market_report(
            analysis,
            analytics_source=analytics_path,
            ai_source=ai_path,
        )
        written_path = write_strategic_market_report(markdown, output_path)
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.exception("Strategic report failed error=%s", error_message)
        return StrategicStageResult(
            strategic_status="failed",
            analytics_input_path=str(analytics_path),
            ai_input_path=str(ai_path),
            output_path=None,
            external_signal_count=0,
            error_message=error_message,
        )
    return StrategicStageResult(
        strategic_status="completed",
        analytics_input_path=str(analytics_path),
        ai_input_path=str(ai_path),
        output_path=str(written_path),
        external_signal_count=external.available_signal_count,
    )


def _analytics_evidence_sha256(analytics: DailyMarketIntelligence) -> str:
    payload = {
        "date": analytics.report_date.isoformat(),
        "vehicles": [asdict(item) for item in analytics.vehicles],
        "brands": [asdict(item) for item in analytics.brands],
        "methodology": analytics.methodology,
    }
    evidence_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
