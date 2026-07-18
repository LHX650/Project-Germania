"""Official price observation repository queries and upserts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import OfficialPriceObservation
from germania.db.repositories.base import BaseRepository
from germania.db.repositories.source import DataSourceRepository

if TYPE_CHECKING:
    from germania.collectors.volkswagen.models import OfficialPriceRecord


@dataclass(frozen=True)
class OfficialPriceUpsertResult:
    """Result summary for one idempotent official price observation write."""

    observation: OfficialPriceObservation
    created: bool = False
    updated: bool = False

    @property
    def unchanged(self) -> bool:
        """Return whether the upsert found an identical existing row."""

        return not self.created and not self.updated


class OfficialPriceRepository(BaseRepository[OfficialPriceObservation]):
    """Repository for official manufacturer price observations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, OfficialPriceObservation)

    def get_by_official_price_key(
        self,
        *,
        vehicle_variant_id: int,
        data_source_id: int,
        valid_date: object,
        official_price: object,
    ) -> OfficialPriceObservation | None:
        """Return one official price row by the schema idempotency key."""

        statement = select(OfficialPriceObservation).where(
            OfficialPriceObservation.vehicle_variant_id == vehicle_variant_id,
            OfficialPriceObservation.data_source_id == data_source_id,
            OfficialPriceObservation.valid_date == valid_date,
            OfficialPriceObservation.official_price == official_price,
        )
        return self.session.scalars(statement).one_or_none()

    def upsert_official_price_record(
        self,
        record: OfficialPriceRecord,
        *,
        vehicle_variant_id: int,
    ) -> OfficialPriceUpsertResult:
        """Insert or update one parsed official price observation."""

        source = DataSourceRepository(self.session).get_by_source_id(record.source_id)
        if source is None:
            msg = (
                "Data source is not available for official price record: "
                f"{record.source_id}"
            )
            raise ValueError(msg)
        if record.price_eur is None or record.valid_date is None:
            msg = "Official price record requires price_eur and valid_date"
            raise ValueError(msg)
        if record.original_currency is None:
            msg = "Official price record requires original_currency"
            raise ValueError(msg)

        existing = self.get_by_official_price_key(
            vehicle_variant_id=vehicle_variant_id,
            data_source_id=source.data_source_id,
            valid_date=record.valid_date,
            official_price=record.price_eur,
        )
        values = _official_price_values(
            record,
            data_source_id=source.data_source_id,
            vehicle_variant_id=vehicle_variant_id,
        )

        if existing is None:
            observation = self.add(OfficialPriceObservation(**values))
            return OfficialPriceUpsertResult(observation=observation, created=True)

        changes = _changed_values(existing, values)
        if not changes:
            return OfficialPriceUpsertResult(observation=existing)

        self.update(existing, changes)
        return OfficialPriceUpsertResult(observation=existing, updated=True)


def _official_price_values(
    record: OfficialPriceRecord,
    *,
    data_source_id: int,
    vehicle_variant_id: int,
) -> dict[str, Any]:
    return {
        "vehicle_variant_id": vehicle_variant_id,
        "data_source_id": data_source_id,
        "collection_batch_id": None,
        "official_price": record.price_eur,
        "currency": record.original_currency,
        "price_includes_vat": record.price_includes_vat,
        "valid_date": record.valid_date,
        "effective_from": record.valid_date,
        "effective_to": None,
        "observed_at": record.observed_at,
        "collected_at": record.collected_at,
        "source_url": record.source_url,
        "source_record_id": _source_record_id(record, vehicle_variant_id),
        "raw_brand": record.raw_brand_name,
        "raw_model": record.raw_model_name,
        "raw_variant_name": record.raw_variant_name,
        "data_quality_status": "valid",
        "validation_status": "passed",
        "notes": _notes(record),
    }


def _source_record_id(
    record: OfficialPriceRecord,
    vehicle_variant_id: int,
) -> str:
    return (
        f"{record.source_id}:{vehicle_variant_id}:{record.valid_date}:"
        f"{record.price_type}:{record.price_eur}"
    )


def _notes(record: OfficialPriceRecord) -> str:
    raw_price_text = record.raw_price_text or ""
    return f"price_type={record.price_type}; raw_price_text={raw_price_text}"


def _changed_values(
    observation: OfficialPriceObservation,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        field_name: value
        for field_name, value in values.items()
        if not _values_equal(getattr(observation, field_name), value)
    }


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return _to_naive_utc(left) == _to_naive_utc(right)
    return left == right


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
