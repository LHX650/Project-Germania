"""Registration observation repository queries and KBA upserts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.collectors.kba.models import RegistrationRecord
from germania.db.models import DataSource, RegistrationObservation
from germania.db.repositories.base import BaseRepository
from germania.db.repositories.source import DataSourceRepository


@dataclass(frozen=True)
class RegistrationObservationUpsertResult:
    """Result summary for one idempotent registration observation write."""

    observation: RegistrationObservation
    created: bool = False
    updated: bool = False

    @property
    def unchanged(self) -> bool:
        """Return whether the upsert found an identical existing row."""

        return not self.created and not self.updated


class RegistrationObservationRepository(BaseRepository[RegistrationObservation]):
    """Repository for registration observations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, RegistrationObservation)

    def get_by_kba_key(
        self,
        *,
        observation_period: str,
        brand_id: int,
        vehicle_id: int,
        fuel_type: str | None,
        source_id: str,
    ) -> RegistrationObservation | None:
        """Return one KBA row by the registration idempotency key."""

        statement = (
            select(RegistrationObservation)
            .join(
                DataSource,
                RegistrationObservation.data_source_id == DataSource.data_source_id,
            )
            .where(
                DataSource.source_id == source_id,
                RegistrationObservation.registration_period == observation_period,
                RegistrationObservation.brand_id == brand_id,
                RegistrationObservation.vehicle_id == vehicle_id,
            )
        )
        if fuel_type is None:
            statement = statement.where(RegistrationObservation.fuel_type.is_(None))
        else:
            statement = statement.where(RegistrationObservation.fuel_type == fuel_type)

        return self.session.scalars(statement).one_or_none()

    def upsert_kba_record(
        self,
        record: RegistrationRecord,
        *,
        brand_id: int,
        vehicle_id: int,
        registration_scope: str = "Germany",
        country_code: str = "DE",
    ) -> RegistrationObservationUpsertResult:
        """Insert or update one parsed KBA registration observation.

        ``registration_scope`` remains a geography such as ``Germany`` and is
        deliberately not used for fuel or powertrain information.
        """

        source = DataSourceRepository(self.session).get_by_source_id(record.source_id)
        if source is None:
            msg = f"Data source is not available for KBA record: {record.source_id}"
            raise ValueError(msg)

        observation_period = _observation_period(record)
        existing = self.get_by_kba_key(
            observation_period=observation_period,
            brand_id=brand_id,
            vehicle_id=vehicle_id,
            fuel_type=record.fuel_type,
            source_id=record.source_id,
        )
        values = _kba_observation_values(
            record,
            data_source_id=source.data_source_id,
            brand_id=brand_id,
            vehicle_id=vehicle_id,
            registration_scope=registration_scope,
            country_code=country_code,
        )

        if existing is None:
            observation = self.add(RegistrationObservation(**values))
            return RegistrationObservationUpsertResult(
                observation=observation,
                created=True,
            )

        changes = _changed_values(existing, values)
        if not changes:
            return RegistrationObservationUpsertResult(observation=existing)

        self.update(existing, changes)
        return RegistrationObservationUpsertResult(observation=existing, updated=True)


def _kba_observation_values(
    record: RegistrationRecord,
    *,
    data_source_id: int,
    brand_id: int,
    vehicle_id: int,
    registration_scope: str,
    country_code: str,
) -> dict[str, Any]:
    observation_period = _observation_period(record)
    fuel_type_key = record.fuel_type or "null"
    return {
        "data_source_id": data_source_id,
        "brand_id": brand_id,
        "vehicle_id": vehicle_id,
        "vehicle_variant_id": None,
        "canonical_brand": record.brand,
        "canonical_model": record.model_series,
        "raw_brand": record.brand,
        "raw_model": record.model_series,
        "registration_count": record.registrations,
        "fuel_type": record.fuel_type,
        "market_share": record.market_share,
        "sales_value": None,
        "sales_metric_type": "new_registration",
        "registration_period": observation_period,
        "registration_scope": registration_scope,
        "region": registration_scope,
        "country_code": country_code,
        "state": None,
        "valid_date": date(record.year, record.month, 1),
        "observed_at": None,
        "collected_at": record.collected_at,
        "source_url": record.source_url,
        "source_record_id": (
            f"{record.source_id}:{observation_period}:{brand_id}:"
            f"{vehicle_id}:{fuel_type_key}"
        ),
        "source_file_name": None,
        "source_page_number": None,
        "data_quality_status": "valid",
        "validation_status": "passed",
        "notes": None,
    }


def _changed_values(
    observation: RegistrationObservation,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        field_name: value
        for field_name, value in values.items()
        if getattr(observation, field_name) != value
    }


def _observation_period(record: RegistrationRecord) -> str:
    return f"{record.year:04d}-{record.month:02d}"
