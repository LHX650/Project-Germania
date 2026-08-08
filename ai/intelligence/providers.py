"""Replaceable external-intelligence and LLM provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from ai.intelligence.models import ExternalEvidence


class IntelligenceProviderError(RuntimeError):
    """Raised when an optional provider is unavailable or returns invalid data."""


@dataclass(frozen=True)
class ExternalQuery:
    """Provider-neutral request for existing or future external intelligence."""

    query: str
    brands: tuple[str, ...] = ()
    vehicles: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    limit: int = 8


ExternalProviderKind = Literal[
    "news",
    "automotive_news",
    "policy_regulation",
    "search",
    "official_brand_news",
    "industry_report",
]


@runtime_checkable
class ExternalIntelligenceProvider(Protocol):
    """Unified interface for news, search, brand-news, and report adapters."""

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""

    @property
    def capabilities(self) -> frozenset[str]:
        """Return supported kinds: news, search, brand_news, industry_report."""

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Return validated source metadata without copying full articles."""


class NewsProvider(ExternalIntelligenceProvider, Protocol):
    """Contract for provider adapters returning automotive news metadata."""


class PolicyRegulationProvider(ExternalIntelligenceProvider, Protocol):
    """Contract for official policy and regulation source adapters."""


class SearchProvider(ExternalIntelligenceProvider, Protocol):
    """Contract for Google/Bing-style search adapters added in the future."""


class OfficialBrandNewsProvider(ExternalIntelligenceProvider, Protocol):
    """Contract for official brand RSS or API adapters."""


class IndustryReportProvider(ExternalIntelligenceProvider, Protocol):
    """Contract for industry association and public-data report adapters."""


class CompositeExternalIntelligenceProvider:
    """Query multiple provider adapters and deduplicate their attributed results."""

    name = "composite_external_intelligence"

    def __init__(self, providers: tuple[ExternalIntelligenceProvider, ...]) -> None:
        self._providers = providers

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the union of configured provider capabilities."""

        return frozenset(
            capability
            for provider in self._providers
            for capability in provider.capabilities
        )

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Return newest unique evidence while isolating optional-provider failures."""

        evidence_by_url: dict[str, ExternalEvidence] = {}
        errors: list[str] = []
        for provider in self._providers:
            try:
                results = provider.search(query)
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            for item in results:
                evidence_by_url.setdefault(item.url, item)
        if not evidence_by_url and errors and len(errors) == len(self._providers):
            raise IntelligenceProviderError("; ".join(errors))
        return tuple(
            sorted(
                evidence_by_url.values(),
                key=lambda item: (item.published_date, item.title),
                reverse=True,
            )[: query.limit]
        )


class EmptyExternalIntelligenceProvider:
    """Safe provider used when no external artifact or API is configured."""

    name = "none"
    capabilities: frozenset[str] = frozenset()

    def search(self, query: ExternalQuery) -> tuple[ExternalEvidence, ...]:
        """Return no evidence without performing network access."""

        del query
        return ()


@dataclass(frozen=True)
class AgentLLMRequest:
    """Grounded prompt request sent to an optional provider adapter."""

    question: str
    intent: str
    evidence_sha256: str
    evidence_json: str
    grounded_draft_markdown: str
    system_prompt: str


@dataclass(frozen=True)
class AgentLLMResult:
    """Provider response tied to the evidence digest it received."""

    markdown: str
    evidence_sha256: str


@runtime_checkable
class AgentLLMProvider(Protocol):
    """Adapter contract suitable for OpenAI, Claude, Gemini, or local models."""

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        """Generate only from supplied evidence or raise provider error."""


class UnavailableConfiguredLLMProvider:
    """Fail closed when a named provider has no installed adapter."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        """Return the configured provider name."""

        return self._name

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        """Raise so the agent safely returns its grounded local draft."""

        del request
        raise IntelligenceProviderError(
            f"The {self._name} adapter is not registered; using local rules."
        )
