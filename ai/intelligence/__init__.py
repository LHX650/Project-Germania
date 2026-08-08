"""Evidence-grounded automotive intelligence agent primitives."""

from ai.intelligence.agent import AutomotiveIntelligenceAgent
from ai.intelligence.api_providers import (
    ClaudeProvider,
    GeminiProvider,
    OpenAIProvider,
)
from ai.intelligence.executive_brief import (
    ExecutiveBrief,
    ExecutiveBriefGenerator,
    write_executive_brief,
)
from ai.intelligence.models import (
    AgentAnswer,
    AgentEvidence,
    AlertEvidence,
    EvidenceRecord,
    ExternalEvidence,
    VehicleEvidence,
)
from ai.intelligence.providers import (
    CompositeExternalIntelligenceProvider,
    ExternalIntelligenceProvider,
    ExternalQuery,
    IndustryReportProvider,
    NewsProvider,
    OfficialBrandNewsProvider,
    PolicyRegulationProvider,
    SearchProvider,
)

__all__ = [
    "AgentAnswer",
    "AgentEvidence",
    "AlertEvidence",
    "AutomotiveIntelligenceAgent",
    "ClaudeProvider",
    "CompositeExternalIntelligenceProvider",
    "EvidenceRecord",
    "ExecutiveBrief",
    "ExecutiveBriefGenerator",
    "ExternalEvidence",
    "ExternalIntelligenceProvider",
    "ExternalQuery",
    "GeminiProvider",
    "IndustryReportProvider",
    "NewsProvider",
    "OfficialBrandNewsProvider",
    "OpenAIProvider",
    "PolicyRegulationProvider",
    "SearchProvider",
    "VehicleEvidence",
    "write_executive_brief",
]
