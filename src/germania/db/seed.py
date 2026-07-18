"""Configuration seed loader for Project Germania."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import DeclarativeBase, Session

from germania.config import load_source_config, load_vehicle_config
from germania.db.models import (
    Brand,
    DataSource,
    DataSourceCategory,
    Vehicle,
    VehicleAlias,
)
from germania.db.repositories import (
    BaseRepository,
    BrandRepository,
    DataSourceRepository,
    VehicleRepository,
)

logger = logging.getLogger(__name__)

_NON_WORD_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


class SeedConfigError(ValueError):
    """Raised when validated configuration conflicts with database state."""


@dataclass
class SeedStats:
    """Created, updated, and unchanged counts for one seed entity type."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def seen(self) -> int:
        """Return the number of configuration entries processed."""

        return self.created + self.updated + self.unchanged


@dataclass
class SeedResult:
    """Seed import summary for configuration-backed tables."""

    brands: SeedStats = field(default_factory=SeedStats)
    vehicles: SeedStats = field(default_factory=SeedStats)
    vehicle_aliases: SeedStats = field(default_factory=SeedStats)
    data_sources: SeedStats = field(default_factory=SeedStats)
    data_source_categories: SeedStats = field(default_factory=SeedStats)

    @property
    def created(self) -> int:
        """Return the total number of newly inserted records."""

        return sum(_stats(self, "created"))

    @property
    def updated(self) -> int:
        """Return the total number of updated records."""

        return sum(_stats(self, "updated"))

    @property
    def unchanged(self) -> int:
        """Return the total number of unchanged records."""

        return sum(_stats(self, "unchanged"))


def seed_configuration(
    session: Session,
    *,
    vehicle_config_path: Path | str | None = None,
    source_config_path: Path | str | None = None,
) -> SeedResult:
    """Load validated YAML configuration and seed database records.

    The caller owns transaction boundaries. Use ``session_scope`` from
    ``germania.db.session`` around this function when running it outside tests.
    """

    vehicle_config = load_vehicle_config(vehicle_config_path)
    source_config = load_source_config(source_config_path)

    result = SeedResult()
    seed_sources(session, source_config, result)
    seed_vehicles(session, vehicle_config, result)
    logger.info(
        "Seeded configuration: created=%s updated=%s unchanged=%s",
        result.created,
        result.updated,
        result.unchanged,
    )
    return result


def seed_sources(
    session: Session,
    source_config: Mapping[str, Any],
    result: SeedResult | None = None,
) -> SeedResult:
    """Seed data sources and source categories from parsed source config."""

    seed_result = result or SeedResult()
    source_repository = DataSourceRepository(session)
    category_repository = BaseRepository(session, DataSourceCategory)
    category_index = _data_source_category_index(category_repository.list())

    for source_entry in source_config["sources"]:
        source = _upsert_data_source(
            source_repository,
            source_entry,
            seed_result.data_sources,
        )
        _upsert_data_source_categories(
            category_repository,
            category_index,
            source,
            source_entry["data_categories"],
            seed_result.data_source_categories,
        )

    return seed_result


def seed_vehicles(
    session: Session,
    vehicle_config: Mapping[str, Any],
    result: SeedResult | None = None,
) -> SeedResult:
    """Seed brands, vehicles, and vehicle aliases from parsed vehicle config."""

    seed_result = result or SeedResult()
    brand_repository = BrandRepository(session)
    vehicle_repository = VehicleRepository(session)
    alias_repository = BaseRepository(session, VehicleAlias)
    alias_index = _vehicle_alias_index(alias_repository.list())

    for brand_values in _brand_values(vehicle_config):
        _upsert_brand(brand_repository, brand_values, seed_result.brands)

    for vehicle_entry in vehicle_config["vehicles"]:
        brand = brand_repository.get_by_name(vehicle_entry["canonical_brand"])
        if brand is None:
            raise SeedConfigError(
                "Brand was not available after brand seed: "
                f"{vehicle_entry['canonical_brand']}"
            )

        vehicle = _upsert_vehicle(
            vehicle_repository,
            brand,
            vehicle_entry,
            seed_result.vehicles,
        )
        _upsert_vehicle_aliases(
            alias_repository,
            alias_index,
            vehicle,
            vehicle_entry,
            seed_result.vehicle_aliases,
        )

    return seed_result


def _upsert_brand(
    repository: BrandRepository,
    values: Mapping[str, Any],
    stats: SeedStats,
) -> Brand:
    existing = repository.get_by_name(values["canonical_brand"])
    if existing is None:
        stats.created += 1
        return repository.add(Brand(**values))

    if _update_if_changed(repository, existing, values):
        stats.updated += 1
    else:
        stats.unchanged += 1
    return existing


def _upsert_vehicle(
    repository: VehicleRepository,
    brand: Brand,
    vehicle_entry: Mapping[str, Any],
    stats: SeedStats,
) -> Vehicle:
    values = {
        "brand_id": brand.brand_id,
        "canonical_model": vehicle_entry["canonical_model"],
        "chinese_model": vehicle_entry["chinese_model"],
        "vehicle_segment": vehicle_entry["vehicle_segment"],
        "body_type": vehicle_entry["body_type"],
        "default_powertrain": vehicle_entry["powertrain"],
        "priority_level": vehicle_entry["priority_level"],
        "active": vehicle_entry["active"],
    }
    existing = repository.get_by_code(brand.brand_id, vehicle_entry["canonical_model"])
    if existing is None:
        stats.created += 1
        return repository.add(Vehicle(**values))

    if _update_if_changed(repository, existing, values):
        stats.updated += 1
    else:
        stats.unchanged += 1
    return existing


def _upsert_vehicle_aliases(
    repository: BaseRepository[VehicleAlias],
    alias_index: dict[str, VehicleAlias],
    vehicle: Vehicle,
    vehicle_entry: Mapping[str, Any],
    stats: SeedStats,
) -> None:
    for alias_text, alias_type in _vehicle_alias_values(vehicle_entry):
        normalized_alias = _normalization_key(alias_text)
        if not normalized_alias:
            continue

        existing = alias_index.get(normalized_alias)
        if existing is None:
            alias = repository.add(
                VehicleAlias(
                    vehicle_id=vehicle.vehicle_id,
                    alias_text=alias_text,
                    normalized_alias=normalized_alias,
                    alias_language=None,
                    alias_type=alias_type,
                )
            )
            alias_index[normalized_alias] = alias
            stats.created += 1
            continue

        if existing.vehicle_id != vehicle.vehicle_id:
            raise SeedConfigError(
                "Vehicle alias conflicts with an existing vehicle: " f"{alias_text}"
            )

        values = {
            "alias_text": alias_text,
            "alias_language": None,
            "alias_type": alias_type,
        }
        if _update_if_changed(repository, existing, values):
            stats.updated += 1
        else:
            stats.unchanged += 1


def _upsert_data_source(
    repository: DataSourceRepository,
    source_entry: Mapping[str, Any],
    stats: SeedStats,
) -> DataSource:
    values = {
        "source_id": source_entry["source_id"],
        "source_name": source_entry["source_name"],
        "source_type": source_entry["source_type"],
        "country_code": source_entry["country_code"],
        "base_url": source_entry["base_url"],
        "update_frequency": source_entry["update_frequency"],
        "authority_level": source_entry["authority_level"],
        "active": source_entry["active"],
        "collection_method": source_entry["collection_method"],
        "notes": source_entry["notes"],
    }
    existing = repository.get_by_source_id(source_entry["source_id"])
    if existing is None:
        stats.created += 1
        return repository.add(DataSource(**values))

    if _update_if_changed(repository, existing, values):
        stats.updated += 1
    else:
        stats.unchanged += 1
    return existing


def _upsert_data_source_categories(
    repository: BaseRepository[DataSourceCategory],
    category_index: dict[tuple[int, str], DataSourceCategory],
    source: DataSource,
    categories: Iterable[str],
    stats: SeedStats,
) -> None:
    for category in categories:
        key = (source.data_source_id, category)
        if key in category_index:
            stats.unchanged += 1
            continue

        source_category = repository.add(
            DataSourceCategory(
                data_source_id=source.data_source_id,
                data_category=category,
            )
        )
        category_index[key] = source_category
        stats.created += 1


def _brand_values(vehicle_config: Mapping[str, Any]) -> list[dict[str, Any]]:
    values_by_brand: dict[str, dict[str, Any]] = {}
    for vehicle in vehicle_config["vehicles"]:
        canonical_brand = vehicle["canonical_brand"]
        values = {
            "canonical_brand": canonical_brand,
            "chinese_brand": vehicle["chinese_brand"],
            "manufacturer": vehicle["manufacturer"],
            "country_of_origin": vehicle["country_of_origin"],
            "active": vehicle["active"],
        }
        existing = values_by_brand.get(canonical_brand)
        if existing is None:
            values_by_brand[canonical_brand] = values
            continue

        _merge_brand_values(existing, values)

    return list(values_by_brand.values())


def _merge_brand_values(
    existing: dict[str, Any],
    incoming: Mapping[str, Any],
) -> None:
    for field_name in ("chinese_brand", "manufacturer", "country_of_origin"):
        if existing[field_name] != incoming[field_name]:
            raise SeedConfigError(
                "Conflicting brand configuration for "
                f"{existing['canonical_brand']}: {field_name}"
            )

    existing["active"] = bool(existing["active"] or incoming["active"])


def _vehicle_alias_values(vehicle_entry: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: dict[str, tuple[str, str]] = {}

    for alias_text, alias_type in _iter_vehicle_alias_values(vehicle_entry):
        normalized_alias = _normalization_key(alias_text)
        if normalized_alias and normalized_alias not in values:
            values[normalized_alias] = (alias_text, alias_type)

    return list(values.values())


def _iter_vehicle_alias_values(
    vehicle_entry: Mapping[str, Any],
) -> Iterable[tuple[str, str]]:
    yield vehicle_entry["canonical_model"], "official"
    yield vehicle_entry["chinese_model"], "common"

    aliases = vehicle_entry.get("aliases", {})
    if isinstance(aliases, Mapping):
        for alias_text in aliases.get("model", []):
            if isinstance(alias_text, str):
                yield alias_text, "common"


def _vehicle_alias_index(aliases: Iterable[VehicleAlias]) -> dict[str, VehicleAlias]:
    return {alias.normalized_alias: alias for alias in aliases}


def _data_source_category_index(
    categories: Iterable[DataSourceCategory],
) -> dict[tuple[int, str], DataSourceCategory]:
    return {
        (category.data_source_id, category.data_category): category
        for category in categories
    }


def _update_if_changed[ModelT: DeclarativeBase](
    repository: BaseRepository[ModelT],
    instance: ModelT,
    values: Mapping[str, Any],
) -> bool:
    changes = {
        field_name: value
        for field_name, value in values.items()
        if getattr(instance, field_name) != value
    }
    if not changes:
        return False

    repository.update(instance, changes)
    return True


def _normalization_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    compacted = _NON_WORD_PATTERN.sub("", without_marks.casefold())
    return compacted.replace("_", "")


def _stats(result: SeedResult, field_name: str) -> Iterable[int]:
    yield getattr(result.brands, field_name)
    yield getattr(result.vehicles, field_name)
    yield getattr(result.vehicle_aliases, field_name)
    yield getattr(result.data_sources, field_name)
    yield getattr(result.data_source_categories, field_name)
