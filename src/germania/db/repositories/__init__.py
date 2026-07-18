"""Repository exports for Project Germania database access."""

from __future__ import annotations

from germania.db.repositories.base import BaseRepository
from germania.db.repositories.brand import BrandRepository
from germania.db.repositories.registration import (
    RegistrationObservationRepository,
    RegistrationObservationUpsertResult,
)
from germania.db.repositories.source import DataSourceRepository
from germania.db.repositories.variant import VariantRepository
from germania.db.repositories.vehicle import VehicleRepository

__all__ = [
    "BaseRepository",
    "BrandRepository",
    "DataSourceRepository",
    "RegistrationObservationRepository",
    "RegistrationObservationUpsertResult",
    "VariantRepository",
    "VehicleRepository",
]
