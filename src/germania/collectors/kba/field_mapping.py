"""Field mapping helpers for KBA FZ10 registration workbooks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

KBA_SOURCE_ID = "kba"
DEFAULT_FUEL_TYPE = "total"

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "year": ("jahr", "year", "berichtsjahr"),
    "month": ("monat", "month", "berichtsmonat", "zulassungsmonat"),
    "brand": ("hersteller", "marke", "fabrikmarke", "brand"),
    "model_series": (
        "handelsname",
        "modellreihe",
        "modell",
        "modellserie",
        "model series",
        "model_series",
    ),
    "registrations": (
        "neuzulassungen",
        "zulassungen",
        "registrierungen",
        "anzahl",
        "insgesamt",
        "gesamt",
        "total",
    ),
    "fuel_type": ("kraftstoffart", "kraftstoff", "antriebsart", "fuel_type", "fuel"),
    "market_share": (
        "marktanteil",
        "marktanteil in %",
        "anteil",
        "anteil in %",
        "share",
        "market_share",
    ),
    "source_url": ("quelle url", "source_url", "source url"),
}

FUEL_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "total": ("insgesamt", "gesamt", "total"),
    "petrol": ("benzin", "otto", "petrol", "gasoline"),
    "diesel": ("diesel",),
    "battery_electric": (
        "elektro",
        "batterieelektrisch",
        "bev",
        "electric",
    ),
    "plug_in_hybrid": ("plug in hybrid", "plug-in-hybrid", "phev"),
    "hybrid": ("hybrid", "hybride"),
    "gas": ("gas", "erdgas", "fluessiggas", "lpg", "cng"),
    "hydrogen": ("wasserstoff", "hydrogen"),
}

SKIP_ROW_MARKERS = frozenset(
    {
        "insgesamt",
        "gesamt",
        "summe",
        "total",
        "zusammen",
    }
)
FOOTNOTE_MARKERS = (
    "fussnote",
    "fussnoten",
    "quelle",
    "copyright",
    "datenstand",
    "methodik",
)
GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "maerz": 3,
    "marz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


@dataclass(frozen=True)
class HeaderMapping:
    """Resolved header columns for one KBA worksheet table."""

    header_row_index: int
    columns: dict[str, int]
    fuel_value_columns: dict[str, int]


def normalize_header(value: object) -> str:
    """Normalize a workbook cell for resilient header matching."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    text = text.replace("%", " % ")
    text = re.sub(r"[_/()]+", " ", text)
    text = re.sub(r"[-–—]+", "-", text)
    text = re.sub(r"\s+", " ", text.casefold()).strip()
    return text


def resolve_field_name(header_value: object) -> str | None:
    """Resolve a source header value to a canonical field name."""
    normalized = normalize_header(header_value)
    if not normalized:
        return None

    for field_name, aliases in FIELD_ALIASES.items():
        if normalized in {normalize_header(alias) for alias in aliases}:
            return field_name
    return None


def resolve_fuel_column(header_value: object) -> str | None:
    """Resolve a wide-format fuel registration column to a canonical fuel type."""
    normalized = normalize_header(header_value)
    if not normalized:
        return None

    return _resolve_fuel_type(normalized)


def resolve_fuel_type_value(value: object) -> str | None:
    """Resolve a fuel type cell value to a canonical fuel type when possible."""
    normalized = normalize_header(value)
    if not normalized:
        return None
    return _resolve_fuel_type(normalized) or str(value).strip()


def _resolve_fuel_type(normalized: str) -> str | None:
    for fuel_type, aliases in FUEL_COLUMN_ALIASES.items():
        normalized_aliases = {normalize_header(alias) for alias in aliases}
        if normalized in normalized_aliases:
            return fuel_type
    return None
