"""Tests for strategic analysis and management report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from strategic.external import (
    ExternalIntelligenceRequest,
    ExternalSignal,
    ExternalSourceSnapshot,
    ExternalSourceStatus,
    ExternalSourceType,
    StrategicImplication,
)
from strategic.pipeline import run_strategic_report_stage


@dataclass(frozen=True)
class OpportunityKBAProvider:
    """Local fixture provider for report integration coverage."""

    name: str = "fixture-kba"

    def fetch_registrations(
        self,
        request: ExternalIntelligenceRequest,
    ) -> ExternalSourceSnapshot:
        return ExternalSourceSnapshot(
            source_type=ExternalSourceType.KBA_REGISTRATIONS,
            provider_name=self.name,
            status=ExternalSourceStatus.AVAILABLE,
            signals=(
                ExternalSignal(
                    signal_id="fixture-opportunity",
                    title="Attributed external opportunity",
                    summary="A fixture-only externally attributed signal.",
                    implication=StrategicImplication.OPPORTUNITY,
                    source_url="https://example.test/fixture-opportunity",
                    observed_at=request.report_date,
                ),
            ),
        )


def test_generates_management_report_with_required_sections(tmp_path: Path) -> None:
    analytics = write_analytics(tmp_path / "analytics.json")
    ai_report = write_ai_report(tmp_path / "ai.md")
    output = tmp_path / "strategic.md"

    result = run_strategic_report_stage(
        analytics_input_path=analytics,
        ai_input_path=ai_report,
        output_path=output,
        enable_external_providers=False,
    )

    markdown = output.read_text(encoding="utf-8")
    assert result.strategic_status == "completed"
    assert result.external_signal_count == 0
    assert "## Market Opportunity" in markdown
    assert "## Competitive Risk" in markdown
    assert "## Strategic Recommendation" in markdown
    assert "Dynamic Motors Alpha" in markdown
    assert "kba_registrations | not_configured" in markdown
    assert "listing inventory is not sales" in markdown


def test_external_provider_signal_is_attributed_in_report(tmp_path: Path) -> None:
    output = tmp_path / "strategic.md"
    result = run_strategic_report_stage(
        analytics_input_path=write_analytics(tmp_path / "analytics.json"),
        ai_input_path=write_ai_report(tmp_path / "ai.md"),
        output_path=output,
        kba_provider=OpportunityKBAProvider(),
    )

    markdown = output.read_text(encoding="utf-8")
    assert result.external_signal_count == 1
    assert "Attributed external opportunity" in markdown
    assert "https://example.test/fixture-opportunity" in markdown
    assert "kba_registrations | fixture-kba | available | 1" in markdown
    assert "## External Evidence Register" in markdown


def test_empty_analytics_generates_explicit_insufficient_data_report(
    tmp_path: Path,
) -> None:
    analytics = tmp_path / "empty.json"
    analytics.write_text(
        json.dumps(
            {
                "date": "2026-07-31",
                "vehicles": [],
                "brands": [],
                "methodology": {},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "strategic.md"

    result = run_strategic_report_stage(
        analytics_input_path=analytics,
        ai_input_path=write_ai_report(tmp_path / "ai.md"),
        output_path=output,
        enable_external_providers=False,
    )

    assert result.strategic_status == "completed"
    markdown = output.read_text(encoding="utf-8")
    assert "No vehicle opportunity can be ranked" in markdown
    assert "No vehicle ranking may be issued from empty input" in markdown


def test_mismatched_input_dates_fail_and_preserve_old_report(tmp_path: Path) -> None:
    output = tmp_path / "strategic.md"
    output.write_text("old valid strategic report", encoding="utf-8")

    result = run_strategic_report_stage(
        analytics_input_path=write_analytics(tmp_path / "analytics.json"),
        ai_input_path=write_ai_report(tmp_path / "ai.md", report_date="2026-07-30"),
        output_path=output,
        enable_external_providers=False,
    )

    assert result.strategic_status == "failed"
    assert "dates do not match" in (result.error_message or "")
    assert output.read_text(encoding="utf-8") == "old valid strategic report"


def test_mismatched_evidence_digest_fails(tmp_path: Path) -> None:
    result = run_strategic_report_stage(
        analytics_input_path=write_analytics(tmp_path / "analytics.json"),
        ai_input_path=write_ai_report(
            tmp_path / "ai.md",
            evidence_sha256="f" * 64,
        ),
        output_path=tmp_path / "strategic.md",
        enable_external_providers=False,
    )

    assert result.strategic_status == "failed"
    assert "SHA-256 does not match" in (result.error_message or "")


def write_analytics(path: Path) -> Path:
    payload = {
        "date": "2026-07-31",
        "vehicles": [
            {
                "vehicle": {"brand": "Dynamic Motors", "model": "Alpha"},
                "metrics": {
                    "active_listing_count": 10,
                    "average_price_eur": 30_000,
                    "minimum_price_eur": 25_000,
                    "maximum_price_eur": 35_000,
                    "price_change_7d_pct": -2.0,
                    "price_change_30d_pct": None,
                    "new_listings_count_7d": 4,
                    "inventory_change_7d_count": 2,
                    "inventory_change_7d_pct": 25.0,
                },
                "opportunity_score": {
                    "score": 82.5,
                    "components": {
                        "inventory_attractiveness": 80.0,
                        "price_competitiveness": 75.0,
                        "price_trend": 60.0,
                        "market_activity": 95.0,
                    },
                    "applied_weights": {
                        "inventory_attractiveness": 0.3,
                        "price_competitiveness": 0.3,
                        "price_trend": 0.2,
                        "market_activity": 0.2,
                    },
                },
            }
        ],
        "brands": [
            {
                "brand": "Dynamic Motors",
                "metrics": {
                    "active_inventory_count": 10,
                    "active_inventory_rank": 1,
                    "average_vehicle_price_eur": 30_000,
                    "bev_share_pct": 100.0,
                    "phev_share_pct": 0.0,
                    "bev_phev_share_pct": 100.0,
                    "model_coverage_count": 1,
                    "catalog_model_count": 1,
                    "model_coverage_pct": 100.0,
                },
            }
        ],
        "methodology": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_ai_report(
    path: Path,
    *,
    report_date: str = "2026-07-31",
    evidence_sha256: str | None = None,
) -> Path:
    digest_line = (
        f"**Analytics evidence SHA-256:** `{evidence_sha256}`  \n"
        if evidence_sha256 is not None
        else ""
    )
    path.write_text(
        f"""# AI Market Report

**Generation mode:** `local_rules`
**LLM provider:** `none`
{digest_line}

**Analytics date:** {report_date}

## Germany market overview

Fixture marketplace summary.

## Vehicle opportunity analysis

- Dynamic Motors Alpha has the highest fixture score.

## Risk and opportunity summary

- **Opportunity:** Dynamic Motors Alpha is a research priority.
- **Activity signal:** Four new listings were observed.
- **Trend-data risk:** Thirty-day history is unavailable.
- **Measurement risk:** Listings are not registrations.
""",
        encoding="utf-8",
    )
    return path
