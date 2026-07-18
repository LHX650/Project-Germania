"""Approved KBA source name mapping loader."""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_KBA_NAME_MAPPING_PATH = PROJECT_ROOT / "config" / "kba_name_mapping.yaml"


class KBANameMappingError(ValueError):
    """Raised when the approved KBA name mapping file is invalid."""


@dataclass(frozen=True)
class KBANameMapping:
    """Read-only approved KBA brand and vehicle name mapping."""

    brand_mappings: Mapping[str, str]
    vehicle_mappings: Mapping[tuple[str, str], tuple[str, str]]
    rejected_vehicle_keys: frozenset[tuple[str, str]]

    _cache: ClassVar[dict[Path, KBANameMapping]] = {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> KBANameMapping:
        """Load and cache the approved KBA mapping YAML."""

        mapping_path = (
            Path(path) if path is not None else DEFAULT_KBA_NAME_MAPPING_PATH
        ).resolve()
        cached = cls._cache.get(mapping_path)
        if cached is not None:
            return cached

        logger.debug("Loading approved KBA name mapping from %s", mapping_path)
        if not mapping_path.exists():
            raise KBANameMappingError(
                f"KBA name mapping file not found: {mapping_path}"
            )

        try:
            with mapping_path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:
            raise KBANameMappingError(
                f"Invalid KBA name mapping YAML in {mapping_path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise KBANameMappingError(
                f"KBA name mapping must be a mapping: {mapping_path}"
            )

        mapping = cls(
            brand_mappings=MappingProxyType(_load_brand_mappings(data, mapping_path)),
            vehicle_mappings=MappingProxyType(
                _load_vehicle_mappings(data, mapping_path)
            ),
            rejected_vehicle_keys=frozenset(
                _load_rejected_vehicle_keys(data, mapping_path)
            ),
        )
        cls._cache[mapping_path] = mapping
        return mapping

    def normalize_brand(self, raw_brand: str) -> str:
        """Return the approved canonical brand name, or the original value."""

        return self.brand_mappings.get(_mapping_key(raw_brand), raw_brand)

    def normalize_vehicle(self, raw_brand: str, raw_model: str) -> tuple[str, str]:
        """Return approved canonical brand and model names, or original values."""

        canonical_brand = self.normalize_brand(raw_brand)
        raw_key = (_mapping_key(raw_brand), _mapping_key(raw_model))
        canonical_key = (_mapping_key(canonical_brand), _mapping_key(raw_model))

        mapped_vehicle = self.vehicle_mappings.get(raw_key)
        if mapped_vehicle is None:
            mapped_vehicle = self.vehicle_mappings.get(canonical_key)
        if mapped_vehicle is not None:
            return mapped_vehicle

        return canonical_brand, raw_model

    def is_rejected_vehicle(self, raw_brand: str, raw_model: str) -> bool:
        """Return whether a brand-model pair was explicitly rejected by review."""

        canonical_brand = self.normalize_brand(raw_brand)
        keys = {
            (_mapping_key(raw_brand), _mapping_key(raw_model)),
            (_mapping_key(canonical_brand), _mapping_key(raw_model)),
        }
        return any(key in self.rejected_vehicle_keys for key in keys)


def _load_brand_mappings(data: dict[str, Any], path: Path) -> dict[str, str]:
    brand_mappings: dict[str, str] = {}
    for index, entry in enumerate(_mapping_list(data, "approved_brand_mappings", path)):
        if entry.get("decision") != "approved":
            continue
        source_value = _required_text(entry, "source_value", path, index)
        canonical_value = _required_text(entry, "canonical_value", path, index)
        brand_mappings[_mapping_key(source_value)] = canonical_value
    return brand_mappings


def _load_vehicle_mappings(
    data: dict[str, Any],
    path: Path,
) -> dict[tuple[str, str], tuple[str, str]]:
    vehicle_mappings: dict[tuple[str, str], tuple[str, str]] = {}
    for index, entry in enumerate(
        _mapping_list(data, "approved_vehicle_mappings", path)
    ):
        if entry.get("decision") != "approved":
            continue
        source_brand = _required_text(entry, "source_brand", path, index)
        source_model = _required_text(entry, "source_model", path, index)
        canonical_brand = _required_text(entry, "canonical_brand", path, index)
        canonical_model = _required_text(entry, "canonical_model", path, index)
        vehicle_mappings[(_mapping_key(source_brand), _mapping_key(source_model))] = (
            canonical_brand,
            canonical_model,
        )
    return vehicle_mappings


def _load_rejected_vehicle_keys(
    data: dict[str, Any],
    path: Path,
) -> set[tuple[str, str]]:
    rejected_keys: set[tuple[str, str]] = set()
    for section in ("rejected_vehicle_mappings", "ambiguous_mappings"):
        for index, entry in enumerate(_mapping_list(data, section, path)):
            if entry.get("decision") != "rejected":
                continue
            source_brand = _required_text(entry, "source_brand", path, index)
            source_model = _required_text(entry, "source_model", path, index)
            rejected_keys.add((_mapping_key(source_brand), _mapping_key(source_model)))
    return rejected_keys


def _mapping_list(data: dict[str, Any], key: str, path: Path) -> list[dict[str, Any]]:
    entries = data.get(key, [])
    if not isinstance(entries, list):
        raise KBANameMappingError(f"{key} must be a list in {path}")
    if not all(isinstance(entry, dict) for entry in entries):
        raise KBANameMappingError(f"{key} entries must be mappings in {path}")
    return entries


def _required_text(
    entry: dict[str, Any],
    field_name: str,
    path: Path,
    index: int,
) -> str:
    value = entry.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise KBANameMappingError(
            f"Missing non-empty {field_name} in {path} mapping row {index}"
        )
    return value.strip()


def _mapping_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    collapsed = "".join(
        character.casefold() if character.isalnum() else " "
        for character in without_marks
    )
    return " ".join(collapsed.split())
