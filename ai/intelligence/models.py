"""Provider-neutral evidence and answer models for the intelligence agent."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlparse

QuestionIntent = Literal[
    "daily_brief",
    "vehicle_pressure",
    "highest_opportunity",
    "market_risk",
    "vehicle_comparison",
    "alert_explanation",
    "general",
]


@dataclass(frozen=True)
class ExternalEvidence:
    """Provider-neutral external evidence metadata; content remains at source."""

    source: str
    title: str
    url: str
    published_date: str
    category: str
    brand: str | None
    vehicle: str | None
    content_summary: str
    reliability: float
    fetched_time: str
    evidence_type: str
    region: str
    image_url: str | None = None
    image_source: str | None = None

    def __post_init__(self) -> None:
        """Reject incomplete or non-attributable provider evidence."""

        required = {
            "source": self.source,
            "title": self.title,
            "category": self.category,
            "content_summary": self.content_summary,
            "fetched_time": self.fetched_time,
            "evidence_type": self.evidence_type,
            "region": self.region,
        }
        missing = tuple(
            name
            for name, value in required.items()
            if not isinstance(value, str) or not value.strip()
        )
        if missing:
            raise ValueError(f"External evidence fields cannot be empty: {missing}")
        if self.brand is not None and not isinstance(self.brand, str):
            raise ValueError("External evidence brand must be text or null.")
        if self.vehicle is not None and not isinstance(self.vehicle, str):
            raise ValueError("External evidence vehicle must be text or null.")
        if self.image_source is not None and (
            not isinstance(self.image_source, str) or not self.image_source.strip()
        ):
            raise ValueError("External evidence image_source must be text or null.")
        if (
            isinstance(self.reliability, bool)
            or not isinstance(self.reliability, (int, float))
            or not math.isfinite(float(self.reliability))
            or not 0 <= float(self.reliability) <= 100
        ):
            raise ValueError("External evidence reliability must be between 0 and 100.")
        if not isinstance(self.url, str):
            raise ValueError("External evidence URL must be an absolute HTTPS URL.")
        parsed_url = urlparse(self.url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("External evidence URL must be an absolute HTTPS URL.")
        if self.image_url is not None:
            if not isinstance(self.image_url, str):
                raise ValueError(
                    "External evidence image_url must be an absolute HTTPS URL."
                )
            parsed_image = urlparse(self.image_url)
            if parsed_image.scheme != "https" or not parsed_image.netloc:
                raise ValueError(
                    "External evidence image_url must be an absolute HTTPS URL."
                )
        if not isinstance(self.published_date, str):
            raise ValueError("External evidence published_date must use ISO-8601.")
        try:
            datetime.fromisoformat(self.published_date.replace("Z", "+00:00"))
        except ValueError:
            try:
                date.fromisoformat(self.published_date)
            except ValueError as exc:
                raise ValueError(
                    "External evidence published_date must use ISO-8601."
                ) from exc
        try:
            fetched = datetime.fromisoformat(self.fetched_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                "External evidence fetched_time must use ISO-8601."
            ) from exc
        if fetched.tzinfo is None:
            raise ValueError("External evidence fetched_time must include a time zone.")


@dataclass(frozen=True)
class AlertEvidence:
    """One existing Market Alerts rule evaluation used as evidence."""

    alert_type: str
    level: str | None
    status: str
    vehicle_key: str
    trigger_reason: str
    related_metrics: tuple[tuple[str, float | int | str | None], ...]
    timestamp: str


@dataclass(frozen=True)
class VehicleEvidence:
    """Current Analytics, peer, alert, and SQLite history for one vehicle."""

    vehicle_key: str
    brand: str
    model: str
    active_listing_count: int
    average_asking_price_eur: float | None
    price_change_7d_pct: float | None
    price_change_30d_pct: float | None
    inventory_change_7d_count: int
    inventory_change_7d_pct: float | None
    new_listings_count_7d: int
    opportunity_score: float
    price_pressure_index: float | None
    inventory_pressure_index: float | None
    market_momentum_score: float | None
    market_momentum_label: str
    peer_status: str
    peer_match_level: int | None
    peer_match_basis: tuple[str, ...]
    peer_sample_size: int
    peer_rank: int | None
    peer_percentile: float | None
    peer_gaps: tuple[tuple[str, float | None], ...]
    price_history: tuple[tuple[str, float | None], ...]
    inventory_history: tuple[tuple[str, int], ...]
    peer_gap_units: tuple[tuple[str, str], ...] = ()

    @property
    def available_signal_count(self) -> int:
        """Return the number of optional quantitative signals that are present."""

        return sum(
            value is not None
            for value in (
                self.average_asking_price_eur,
                self.price_change_7d_pct,
                self.price_change_30d_pct,
                self.inventory_change_7d_pct,
                self.price_pressure_index,
                self.inventory_pressure_index,
                self.market_momentum_score,
            )
        )


@dataclass(frozen=True)
class AgentEvidence:
    """Complete evidence packet supplied to local rules or an optional LLM."""

    question: str
    intent: QuestionIntent
    analytics_date: str | None
    vehicles: tuple[VehicleEvidence, ...] = ()
    alerts: tuple[AlertEvidence, ...] = ()
    external: tuple[ExternalEvidence, ...] = ()
    external_status: str = "insufficient_data"
    data_gaps: tuple[str, ...] = ()

    @property
    def has_evidence(self) -> bool:
        """Return whether at least one verified internal or external item exists."""

        return bool(self.vehicles or self.alerts or self.external)

    def canonical_json(self) -> str:
        """Serialize evidence deterministically for provider grounding checks."""

        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        """Return the digest of the exact evidence packet."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    """One display-ready evidence citation with source and observation time."""

    evidence_source: str
    metric_name: str
    value: str
    timestamp: str
    vehicle_key: str | None = None


@dataclass(frozen=True)
class AgentAnswer:
    """Six-section evidence-based answer rendered by the Dashboard."""

    situation_summary: str
    evidence: tuple[str, ...]
    key_drivers: tuple[str, ...]
    competitive_implication: str
    recommended_monitoring_actions: tuple[str, ...]
    confidence_level: str
    generation_mode: str
    provider_name: str
    evidence_sha256: str
    evidence_records: tuple[EvidenceRecord, ...] = ()

    def to_markdown(self) -> str:
        """Render the required answer structure as Markdown."""

        evidence = "\n".join(f"- {item}" for item in self.evidence)
        drivers = "\n".join(f"- {item}" for item in self.key_drivers)
        actions = "\n".join(f"- {item}" for item in self.recommended_monitoring_actions)
        return (
            "## Situation Summary\n\n"
            f"{self.situation_summary}\n\n"
            "## Evidence\n\n"
            f"{evidence}\n\n"
            "## Key Drivers\n\n"
            f"{drivers}\n\n"
            "## Competitive Implication\n\n"
            f"{self.competitive_implication}\n\n"
            "## Recommended Monitoring Actions\n\n"
            f"{actions}\n\n"
            "## Confidence Level\n\n"
            f"{self.confidence_level}\n"
        )
