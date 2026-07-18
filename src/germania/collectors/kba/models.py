"""Parsed KBA registration records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class RegistrationRecord:
    """Normalized KBA FZ10 monthly registration observation."""

    source_id: str
    year: int
    month: int
    brand: str
    model_series: str
    registrations: int
    fuel_type: str | None
    market_share: Decimal | None
    source_url: str | None
    collected_at: datetime
