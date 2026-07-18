"""Vehicle repository queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from germania.db.models import Vehicle
from germania.db.repositories.base import BaseRepository


class VehicleRepository(BaseRepository[Vehicle]):
    """Repository for canonical vehicle model records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Vehicle)

    def get_by_code(self, brand_id: int, canonical_model: str) -> Vehicle | None:
        """Return a vehicle by the current unique model code.

        The current schema does not have a standalone ``vehicle_code`` field, so
        the stable lookup key is ``brand_id`` plus ``canonical_model``.
        """

        statement = select(Vehicle).where(
            Vehicle.brand_id == brand_id,
            Vehicle.canonical_model == canonical_model,
        )
        return self.session.scalars(statement).one_or_none()

    def list_by_brand(
        self,
        brand_id: int,
        *,
        active: bool | None = None,
    ) -> list[Vehicle]:
        """Return vehicles for one brand, optionally filtered by active state."""

        statement = select(Vehicle).where(Vehicle.brand_id == brand_id)
        if active is not None:
            statement = statement.where(Vehicle.active.is_(active))

        statement = statement.order_by(Vehicle.canonical_model)
        return list(self.session.scalars(statement).all())

    def list_active(self) -> list[Vehicle]:
        """Return active vehicles ordered by brand and model."""

        statement = (
            select(Vehicle)
            .where(Vehicle.active.is_(True))
            .order_by(Vehicle.brand_id, Vehicle.canonical_model)
        )
        return list(self.session.scalars(statement).all())
