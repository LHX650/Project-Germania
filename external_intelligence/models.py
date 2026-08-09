"""Normalized external-intelligence records and JSON serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class KBARegistration:
    """One official KBA FZ10 monthly registration observation."""

    period: str
    brand: str
    model: str
    registrations: int
    fuel_type: str | None
    country: str
    source: str
    source_url: str
    retrieved_at: datetime

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible record."""

        payload = asdict(self)
        payload["retrieved_at"] = self.retrieved_at.isoformat()
        return payload


@dataclass(frozen=True)
class NewsArticle:
    """One attributed RSS, Atom, or structured official-news item."""

    article_id: str
    title: str
    summary: str
    url: str
    source: str
    source_url: str
    published_at: datetime
    brands: tuple[str, ...]
    models: tuple[str, ...]
    country: str
    tags: tuple[str, ...]
    official_brand_news: bool
    image_url: str | None = None
    image_source: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible record."""

        payload = asdict(self)
        payload["published_at"] = self.published_at.isoformat()
        payload["brands"] = list(self.brands)
        payload["models"] = list(self.models)
        payload["tags"] = list(self.tags)
        return payload


@dataclass(frozen=True)
class SourceRun:
    """Observable state for one configured external source."""

    source_id: str
    source: str
    source_url: str
    status: str
    cache_status: str | None
    updated_at: datetime | None
    ttl_seconds: int
    record_count: int
    limitation: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible source state."""

        payload = asdict(self)
        payload["updated_at"] = (
            None if self.updated_at is None else self.updated_at.isoformat()
        )
        return payload
