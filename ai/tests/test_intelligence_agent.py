from __future__ import annotations

from dataclasses import dataclass

from ai.intelligence.agent import (
    NO_EVIDENCE_MESSAGE,
    AutomotiveIntelligenceAgent,
)
from ai.intelligence.models import AgentEvidence, VehicleEvidence
from ai.intelligence.providers import (
    AgentLLMRequest,
    AgentLLMResult,
    IntelligenceProviderError,
)
from ai.intelligence.retrieval import classify_question, mentioned_vehicle_keys


def test_empty_evidence_returns_exact_insufficient_message() -> None:
    evidence = AgentEvidence(
        question="What is happening?",
        intent="general",
        analytics_date=None,
    )

    answer = AutomotiveIntelligenceAgent().answer(evidence)

    assert answer.situation_summary == NO_EVIDENCE_MESSAGE
    assert answer.confidence_level == "Insufficient"
    assert NO_EVIDENCE_MESSAGE in answer.to_markdown()


def test_local_answer_contains_all_required_sections_and_real_signals() -> None:
    evidence = AgentEvidence(
        question="Why is Dynamic Alpha under pressure?",
        intent="vehicle_pressure",
        analytics_date="2026-08-07",
        vehicles=(_vehicle(),),
    )

    answer = AutomotiveIntelligenceAgent().answer(evidence)
    markdown = answer.to_markdown()

    assert answer.generation_mode == "local_rules"
    assert "Dynamic Alpha" in markdown
    assert "7-day asking-price change -4.00%" in markdown
    assert "listing inventory" in markdown
    assert "transaction price" not in answer.situation_summary.casefold()
    for heading in (
        "Situation Summary",
        "Evidence",
        "Key Drivers",
        "Competitive Implication",
        "Recommended Monitoring Actions",
        "Confidence Level",
    ):
        assert f"## {heading}" in markdown
    records = {
        (item.evidence_source, item.metric_name) for item in answer.evidence_records
    }
    assert ("Daily Market Intelligence", "Vehicle Opportunity Score") in records
    assert ("Quantitative Intelligence", "Price Pressure Index") in records
    assert ("Quantitative Intelligence", "Inventory Pressure Index") in records
    assert ("Peer Benchmark", "Peer Rank") in records


def test_unavailable_api_falls_back_without_losing_grounded_answer() -> None:
    provider = _FailingProvider()
    evidence = AgentEvidence(
        question="Why is Dynamic Alpha under pressure?",
        intent="vehicle_pressure",
        analytics_date="2026-08-07",
        vehicles=(_vehicle(),),
    )

    answer = AutomotiveIntelligenceAgent(provider).answer(evidence)

    assert answer.generation_mode == "local_rules_fallback"
    assert answer.provider_name == "unavailable-api"
    assert "Dynamic Alpha" in answer.situation_summary


def test_llm_number_absent_from_evidence_is_rejected() -> None:
    evidence = AgentEvidence(
        question="Why is Dynamic Alpha under pressure?",
        intent="vehicle_pressure",
        analytics_date="2026-08-07",
        vehicles=(_vehicle(),),
    )

    answer = AutomotiveIntelligenceAgent(_InventingProvider()).answer(evidence)

    assert answer.generation_mode == "local_rules_fallback"
    assert "999" not in answer.to_markdown()


def test_question_classification_and_vehicle_matching_are_dynamic() -> None:
    keys = ("Dynamic Alpha", "Example Beta")

    assert classify_question("Compare Example Beta versus Dynamic Alpha") == (
        "vehicle_comparison"
    )
    assert mentioned_vehicle_keys(
        "Compare Example Beta versus Dynamic Alpha",
        keys,
    ) == ("Example Beta", "Dynamic Alpha")


def _vehicle() -> VehicleEvidence:
    return VehicleEvidence(
        vehicle_key="Dynamic Alpha",
        brand="Dynamic",
        model="Alpha",
        active_listing_count=100,
        average_asking_price_eur=50_000,
        price_change_7d_pct=-4,
        price_change_30d_pct=-2,
        inventory_change_7d_count=15,
        inventory_change_7d_pct=15,
        new_listings_count_7d=20,
        opportunity_score=75,
        price_pressure_index=70,
        inventory_pressure_index=65,
        market_momentum_score=42,
        market_momentum_label="Neutral",
        peer_status="ok",
        peer_match_level=1,
        peer_match_basis=("segment", "powertrain"),
        peer_sample_size=3,
        peer_rank=2,
        peer_percentile=50,
        peer_gaps=(("price", -3.5),),
        price_history=(("2026-08-07", 50_000),),
        inventory_history=(("2026-08-07", 100),),
        peer_gap_units=(("price", "percent"),),
    )


@dataclass(frozen=True)
class _FailingProvider:
    name: str = "unavailable-api"

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        del request
        raise IntelligenceProviderError("API unavailable")


@dataclass(frozen=True)
class _InventingProvider:
    name: str = "inventing-api"

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        markdown = request.grounded_draft_markdown.replace(
            "## Situation Summary",
            "## Situation Summary\n\nUnsupported 999 registrations.\n",
        )
        return AgentLLMResult(
            markdown=markdown,
            evidence_sha256=request.evidence_sha256,
        )
