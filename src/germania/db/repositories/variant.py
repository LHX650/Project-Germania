"""Vehicle variant repository queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import VehicleVariant
from germania.db.repositories.base import BaseRepository


class VariantRepository(BaseRepository[VehicleVariant]):
    """Repository for vehicle variant records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, VehicleVariant)

    def list_by_vehicle(
        self,
        vehicle_id: int,
        *,
        active: bool | None = None,
    ) -> list[VehicleVariant]:
        """Return variants for one vehicle, optionally filtered by active state."""

        statement = select(VehicleVariant).where(
            VehicleVariant.vehicle_id == vehicle_id
        )
        if active is not None:
            statement = statement.where(VehicleVariant.active.is_(active))

        statement = statement.order_by(
            VehicleVariant.model_year,
            VehicleVariant.trim_name,
            VehicleVariant.variant_name,
            VehicleVariant.edition_name,
            VehicleVariant.vehicle_variant_id,
        )
        return list(self.session.scalars(statement).all())
