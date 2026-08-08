from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai.intelligence.executive_brief import (
    BRIEF_HEADINGS,
    ExecutiveBriefGenerator,
    write_executive_brief,
)
from ai.intelligence.models import (
    AgentEvidence,
    AlertEvidence,
    ExternalEvidence,
    VehicleEvidence,
)
from ai.intelligence.providers import AgentLLMRequest, AgentLLMResult


def test_local_brief_contains_all_sections_and_separates_evidence() -> None:
    evidence = _evidence()

    brief = ExecutiveBriefGenerator().generate(
        evidence,
        generated_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    markdown = brief.to_markdown()

    assert all(heading in markdown for heading in BRIEF_HEADINGS)
    assert "## Internal Market Evidence" in markdown
    assert "## External Market Signals" in markdown
    assert "Tesla Model Y" in markdown
    assert "https://example.org/policy" in markdown
    assert brief.evidence_sha256 == evidence.sha256()
    assert brief.has_internal_evidence
    assert brief.has_external_evidence
    assert "not transaction prices or vehicle sales" in markdown
    assert "External Market Signals include 1 verified items" in markdown


def test_empty_evidence_returns_insufficient_data() -> None:
    evidence = AgentEvidence(
        question="Daily market brief",
        intent="daily_brief",
        analytics_date=None,
        data_gaps=("Analytics unavailable.",),
    )

    brief = ExecutiveBriefGenerator().generate(evidence)

    assert brief.executive_summary == "insufficient_data"
    assert brief.critical_risks == ("insufficient_data",)
    assert brief.confidence_level == "Insufficient"
    assert not brief.internal_evidence
    assert not brief.external_evidence


def test_llm_provider_uses_same_evidence_digest() -> None:
    provider = _EchoProvider()
    evidence = _evidence()

    brief = ExecutiveBriefGenerator(provider).generate(evidence)

    assert brief.generation_mode == "llm_grounded"
    assert brief.provider_name == "echo"
    assert provider.request is not None
    assert provider.request.evidence_sha256 == evidence.sha256()


def test_llm_unsupported_number_falls_back_to_local_rules() -> None:
    brief = ExecutiveBriefGenerator(_InventingProvider()).generate(_evidence())

    assert brief.generation_mode == "local_rules_fallback"
    assert brief.provider_name == "inventing"
    assert "999.99" not in brief.to_markdown()


def test_llm_external_causality_claim_falls_back_to_local_rules() -> None:
    brief = ExecutiveBriefGenerator(_CausalProvider()).generate(_evidence())

    assert brief.generation_mode == "local_rules_fallback"
    assert "caused the internal" not in brief.to_markdown()


def test_atomic_writer_preserves_old_artifact_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "daily_executive_intelligence_brief.md"
    output.write_text("old valid report", encoding="utf-8")
    brief = ExecutiveBriefGenerator().generate(_evidence())
    original_replace = Path.replace

    def fail_replace(path: Path, target: Path) -> Path:
        if path.suffix == ".tmp":
            raise OSError("simulated atomic replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated atomic replace failure"):
        write_executive_brief(brief, output)

    assert output.read_text(encoding="utf-8") == "old valid report"
    assert not output.with_suffix(".md.tmp").exists()


def _evidence() -> AgentEvidence:
    return AgentEvidence(
        question="Daily market brief",
        intent="daily_brief",
        analytics_date="2026-08-08",
        vehicles=(
            VehicleEvidence(
                vehicle_key="Tesla Model Y",
                brand="Tesla",
                model="Model Y",
                active_listing_count=50,
                average_asking_price_eur=45_000,
                price_change_7d_pct=-5.0,
                price_change_30d_pct=-7.0,
                inventory_change_7d_count=10,
                inventory_change_7d_pct=25.0,
                new_listings_count_7d=12,
                opportunity_score=62.0,
                price_pressure_index=75.0,
                inventory_pressure_index=72.0,
                market_momentum_score=35.0,
                market_momentum_label="Negative",
                peer_status="ok",
                peer_match_level=1,
                peer_match_basis=("segment", "powertrain", "price_band"),
                peer_sample_size=5,
                peer_rank=4,
                peer_percentile=25.0,
                peer_gaps=(
                    ("price_gap_pct", -8.0),
                    ("opportunity_score_gap", 2.0),
                    ("market_momentum_gap", -10.0),
                ),
                price_history=(("2026-08-08", 45_000),),
                inventory_history=(("2026-08-08", 50),),
            ),
        ),
        alerts=(
            AlertEvidence(
                alert_type="Price Drop Alert",
                level="Warning",
                status="available",
                vehicle_key="Tesla Model Y",
                trigger_reason="7-day asking price decreased by 5.00%.",
                related_metrics=(("price_change_7d_pct", -5.0),),
                timestamp="2026-08-08T00:00:00+00:00",
            ),
        ),
        external=(
            ExternalEvidence(
                source="Official Authority",
                title="German automotive policy update",
                url="https://example.org/policy",
                published_date="2026-08-07",
                category="policy_regulation",
                brand=None,
                vehicle=None,
                content_summary="Official policy metadata.",
                reliability=95,
                fetched_time="2026-08-08T00:00:00+00:00",
                evidence_type="official_policy",
                region="DE",
            ),
        ),
    )


class _EchoProvider:
    name = "echo"

    def __init__(self) -> None:
        self.request: AgentLLMRequest | None = None

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        self.request = request
        return AgentLLMResult(
            markdown=request.grounded_draft_markdown,
            evidence_sha256=request.evidence_sha256,
        )


class _InventingProvider:
    name = "inventing"

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        return AgentLLMResult(
            markdown=request.grounded_draft_markdown.replace("62.00", "999.99"),
            evidence_sha256=request.evidence_sha256,
        )


class _CausalProvider:
    name = "causal"

    def generate(self, request: AgentLLMRequest) -> AgentLLMResult:
        return AgentLLMResult(
            markdown=request.grounded_draft_markdown.replace(
                "Official Authority | Policy Regulation |",
                "Official Authority caused the internal price decline |",
            ),
            evidence_sha256=request.evidence_sha256,
        )
