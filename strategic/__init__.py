"""Independent strategic intelligence layer for Project Germania."""

from strategic.ai_input import AIReportEvidence, AIReportInputError
from strategic.analysis import (
    EvidenceLevel,
    StrategicAnalysis,
    StrategicFinding,
    StrategicRecommendation,
    build_strategic_analysis,
)
from strategic.external import (
    BrandNewsDataProvider,
    ExternalIntelligenceBundle,
    ExternalIntelligenceRequest,
    ExternalMarketDataProvider,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    KBADataProvider,
    NewsDataProvider,
    StrategicImplication,
    collect_external_intelligence,
)

__all__ = [
    "AIReportEvidence",
    "AIReportInputError",
    "EvidenceLevel",
    "ExternalIntelligenceBundle",
    "ExternalIntelligenceRequest",
    "ExternalMarketDataProvider",
    "BrandNewsDataProvider",
    "ExternalSignal",
    "ExternalSourceSnapshot",
    "ExternalSourceStatus",
    "ExternalSourceType",
    "KBADataProvider",
    "NewsDataProvider",
    "StrategicAnalysis",
    "StrategicFinding",
    "StrategicImplication",
    "StrategicRecommendation",
    "StrategicStageResult",
    "build_strategic_analysis",
    "collect_external_intelligence",
    "run_strategic_report_stage",
]


def __getattr__(name: str) -> object:
    """Lazily expose pipeline symbols to avoid provider import cycles."""

    if name in {"StrategicStageResult", "run_strategic_report_stage"}:
        from strategic.pipeline import (
            StrategicStageResult,
            run_strategic_report_stage,
        )

        return {
            "StrategicStageResult": StrategicStageResult,
            "run_strategic_report_stage": run_strategic_report_stage,
        }[name]
    raise AttributeError(name)
